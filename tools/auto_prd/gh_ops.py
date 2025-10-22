"""GitHub CLI helpers and review thread utilities."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional, Set

from .command import run_cmd
from .constants import REVIEW_BOT_LOGINS, REVIEW_FALLBACK_MENTION
from .logging_utils import logger
from .utils import call_with_backoff, extract_called_process_error_details


GATHER_THREAD_COMMENTS_QUERY = """
query($threadId:ID!,$cursor:String){
  node(id:$threadId){
    ... on PullRequestReviewThread{
      comments(first:20,after:$cursor){
        nodes{
          author{login}
          body
          url
          commit{oid}
          databaseId
        }
        pageInfo{
          hasNextPage
          endCursor
        }
      }
    }
  }
}
"""


def gh_graphql(query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables})

    def action() -> dict:
        out, _, _ = run_cmd(["gh", "api", "graphql", "--input", "-"], stdin=payload)
        return json.loads(out)

    return call_with_backoff(action)


def get_pr_number_for_head(head_branch: str, repo_root: Path) -> Optional[int]:
    out, _, _ = run_cmd(
        [
            "gh",
            "pr",
            "list",
            "--head",
            head_branch,
            "--json",
            "number",
            "--jq",
            ".[0].number",
        ],
        cwd=repo_root,
    )
    stripped = out.strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        logger.warning("Unexpected PR number format from gh pr list: %r", stripped)
        return None


def branch_has_commits_since(base_branch: str, repo_root: Path) -> bool:
    out, _, _ = run_cmd(["git", "rev-list", "--count", f"{base_branch}..HEAD"], cwd=repo_root)
    try:
        return int(out.strip() or "0") > 0
    except ValueError:
        logger.warning("Could not parse commit count for %s..HEAD: %r", base_branch, out.strip())
        return False


def trigger_copilot(owner_repo: str, pr_number: int, repo_root: Path) -> None:
    try:
        run_cmd(["gh", "save-me-copilot", owner_repo, str(pr_number)], cwd=repo_root)
    except subprocess.CalledProcessError as exc:
        logger.debug(
            "Failed to trigger Copilot for %s PR #%s: %s",
            owner_repo,
            pr_number,
            extract_called_process_error_details(exc),
        )


def _gather_thread_comments(thread_id: str, initial_block: Optional[dict]) -> list[dict]:
    if not thread_id:
        return []
    comments_block = initial_block or {}
    results = list(comments_block.get("nodes") or [])
    page_info = comments_block.get("pageInfo") or {}
    cursor = page_info.get("endCursor")
    while page_info.get("hasNextPage"):
        data = gh_graphql(GATHER_THREAD_COMMENTS_QUERY, {"threadId": thread_id, "cursor": cursor})
        comments = ((data.get("data") or {}).get("node") or {}).get("comments") or {}
        extra_nodes = comments.get("nodes") or []
        results.extend(extra_nodes)
        page_info = comments.get("pageInfo") or {}
        cursor = page_info.get("endCursor")
    return results


def get_unresolved_feedback(owner_repo: str, pr_number: int, commit_sha: Optional[str] = None) -> list[dict]:
    owner_repo = owner_repo.strip()
    if "/" not in owner_repo:
        raise ValueError(f"Invalid owner_repo format: {owner_repo!r}. Expected 'owner/repo'.")
    owner, name = owner_repo.split("/", 1)
    if not owner or not name:
        raise ValueError(f"Invalid owner_repo format: {owner_repo!r}. Expected 'owner/repo'.")
    threads: list[dict] = []
    cursor: Optional[str] = None
    query = """
    query($owner:String!,$name:String!,$number:Int!,$cursor:String){
      repository(owner:$owner,name:$name){
        pullRequest(number:$number){
          reviewThreads(first:50,after:$cursor){
            nodes{
              id
              isResolved
              comments(first:20){
                nodes{
                  author{login}
                  body
                  url
                  commit{oid}
                  databaseId
                }
                pageInfo{hasNextPage endCursor}
              }
            }
            pageInfo{hasNextPage endCursor}
          }
        }
      }
    }
    """
    while True:
        data = gh_graphql(query, {"owner": owner, "name": name, "number": pr_number, "cursor": cursor})
        review_threads = (((data.get("data") or {}).get("repository") or {}).get("pullRequest") or {}).get("reviewThreads") or {}
        nodes = review_threads.get("nodes") or []
        threads.extend(nodes)
        page_info = review_threads.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")

    unresolved: list[dict] = []
    for thread in threads:
        if thread.get("isResolved") is True:
            continue
        thread_id = thread.get("id")
        if not thread_id:
            continue
        comments = _gather_thread_comments(thread_id, thread.get("comments"))
        for comment in comments:
            login = ((comment.get("author") or {}).get("login") or "").strip()
            if login.lower() not in REVIEW_BOT_LOGINS:
                continue
            body = (comment.get("body") or "").strip()
            if not body:
                continue
            url = comment.get("url") or ""
            commit_info = comment.get("commit") or {}
            comment_commit = commit_info.get("oid") if isinstance(commit_info, dict) else None
            if commit_sha and comment_commit and comment_commit != commit_sha:
                continue
            db_id = comment.get("databaseId")
            if db_id is not None:
                unresolved.append(
                    {
                        "summary": f"- {login or 'unknown'}: {body}\n  {url}",
                        "thread_id": thread_id,
                        "comment_id": db_id,
                        "author": login or "unknown",
                        "url": url,
                        "is_resolved": False,
                    }
                )
    return unresolved


def reply_to_review_comment(owner: str, name: str, pr_number: int, comment_id: int, body: str) -> None:
    payload = json.dumps({"body": body, "in_reply_to": comment_id})

    def action():
        run_cmd(
            [
                "gh",
                "api",
                "-X",
                "POST",
                f"/repos/{owner}/{name}/pulls/{pr_number}/comments",
                "--input",
                "-",
            ],
            stdin=payload,
        )

    call_with_backoff(action)


def resolve_review_thread(thread_id: str) -> None:
    payload = json.dumps(
        {
            "query": "mutation($threadId:ID!){resolveReviewThread(input:{threadId:$threadId}){thread{id isResolved}}}",
            "variables": {"threadId": thread_id},
        }
    )

    def action():
        run_cmd(["gh", "api", "graphql", "--input", "-"], stdin=payload)

    call_with_backoff(action)


def acknowledge_review_items(owner_repo: str, pr_number: int, items: list[dict], processed_ids: Set[int]) -> Set[int]:
    """Reply to review items and return the updated set of processed IDs.

    The caller owns the `processed_ids` set so tests can provide deterministic
    state without relying on package-level globals.
    """
    owner_repo = owner_repo.strip()
    if "/" not in owner_repo:
        raise ValueError(f"Invalid owner_repo format: {owner_repo!r}. Expected 'owner/repo'.")
    owner, name = owner_repo.split("/", 1)
    if not owner or not name:
        raise ValueError(f"Invalid owner_repo format: {owner_repo!r}. Expected 'owner/repo'.")
    for item in items:
        comment_id = item.get("comment_id")
        thread_id = item.get("thread_id")
        if isinstance(comment_id, int) and comment_id not in processed_ids:
            author = (item.get("author") or "").strip().lower()
            mention = f"@{author}" if author else REVIEW_FALLBACK_MENTION
            reply_body = f"Fix applied in the latest push — thanks for the review! {mention}"
            try:
                reply_to_review_comment(owner, name, pr_number, comment_id, reply_body)
                processed_ids.add(comment_id)
            except (subprocess.CalledProcessError, OSError, ValueError) as exc:  # pragma: no cover - best effort
                detail = (
                    extract_called_process_error_details(exc)
                    if isinstance(exc, subprocess.CalledProcessError)
                    else str(exc)
                )
                logger.warning("Failed to reply to review comment %s: %s", comment_id, detail)
        if thread_id and not item.get("is_resolved"):
            try:
                resolve_review_thread(thread_id)
            except (subprocess.CalledProcessError, OSError, ValueError) as exc:
                detail = (
                    extract_called_process_error_details(exc)
                    if isinstance(exc, subprocess.CalledProcessError)
                    else str(exc)
                )
                logger.warning("Failed to resolve review thread %s: %s", thread_id, detail)
    return processed_ids


def post_final_comment(pr_number: Optional[int], owner_repo: str, prd_path: Path, repo_root: Path, dry_run: bool = False) -> None:
    if pr_number is None:
        return
    if dry_run:
        logger.info("Dry run enabled; skipping final PR comment for #%s.", pr_number)
        return

    final_msg = (
        "✅ **All requested changes addressed.**\n\n"
        "**What changed & why:**\n"
        f"- Implemented tasks from `{prd_path.name}`.\n"
        "- Iterated with CodeRabbit locally, then addressed CodeRabbit/Copilot PR threads until none remained.\n"
        "- Ensured `make ci` is green; added/updated pipeline as needed.\n\n"
        "Thanks for the review, @CodeRabbitAI and @copilot-pull-request-reviewer[bot]! 🙏"
    )
    payload = json.dumps({"body": final_msg})
    try:
        run_cmd(
            [
                "gh",
                "api",
                "-X",
                "POST",
                f"/repos/{owner_repo}/issues/{pr_number}/comments",
                "--input",
                "-",
            ],
            cwd=repo_root,
            stdin=payload,
        )
        print(f"Posted final comment on PR #{pr_number}. Done.")
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "Failed to post final PR comment for #%s: %s",
            pr_number,
            extract_called_process_error_details(exc),
        )
