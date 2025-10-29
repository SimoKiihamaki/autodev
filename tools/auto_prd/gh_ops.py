"""GitHub CLI helpers and review thread utilities."""

from __future__ import annotations

from datetime import datetime
import json
import subprocess
from pathlib import Path
from typing import Optional, Set, Tuple

from .command import run_cmd
from .constants import (
    CODERABBIT_REVIEW_LOGINS,
    COPILOT_REVIEW_LOGINS,
    REVIEW_BOT_LOGINS,
)
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

REVIEW_THREADS_QUERY = """
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
            pageInfo{
              hasNextPage
              endCursor
            }
          }
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

COMMIT_STATUS_ROLLUP_QUERY = """
query($owner:String!,$name:String!,$oid:GitObjectID!){
  repository(owner:$owner,name:$name){
    object(oid:$oid){
      ... on Commit{
        statusCheckRollup{
          contexts(last:50){
            nodes{
              __typename
              ... on CheckRun{
                name
                conclusion
              }
              ... on StatusContext{
                context
                state
              }
            }
          }
        }
      }
    }
  }
}
"""

PR_ACTIVITY_SNAPSHOT_QUERY = """
query($owner:String!,$name:String!,$number:Int!){
  repository(owner:$owner,name:$name){
    pullRequest(number:$number){
      comments(last:50){
        nodes{
          author{login}
          createdAt
        }
      }
      reviews(last:50){
        nodes{
          author{login}
          submittedAt
          body
        }
      }
    }
  }
}
"""


def _parse_owner_repo(owner_repo: str) -> tuple[str, str]:
    stripped = (owner_repo or "").strip()
    if "/" not in stripped:
        raise ValueError(
            f"Invalid owner_repo format: {owner_repo!r}. Expected 'owner/repo'."
        )
    owner, name = stripped.split("/", 1)
    if not owner or not name:
        raise ValueError(
            f"Invalid owner_repo format: {owner_repo!r}. Expected 'owner/repo'."
        )
    return owner, name


def gh_graphql(query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables})

    def action() -> dict:
        out, _, _ = run_cmd(
            ["gh", "api", "graphql", "--input", "-"], stdin=payload, timeout=60
        )
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
    """Return True when HEAD has commits newer than base_branch (compares base_branch..HEAD)."""
    out, _, _ = run_cmd(
        ["git", "rev-list", "--count", f"{base_branch}..HEAD"], cwd=repo_root
    )
    try:
        return int(out.strip() or "0") > 0
    except ValueError:
        logger.warning(
            "Could not parse commit count for %s..HEAD: %r", base_branch, out.strip()
        )
        return False


def trigger_copilot(owner_repo: str, pr_number: int, repo_root: Path) -> None:
    try:
        run_cmd(
            ["gh", "save-me-copilot", owner_repo, str(pr_number)],
            cwd=repo_root,
            capture=False,
            timeout=30,
        )
    except subprocess.CalledProcessError as exc:
        logger.debug(
            "Failed to trigger Copilot for %s PR #%s: %s",
            owner_repo,
            pr_number,
            extract_called_process_error_details(exc),
        )


def _gather_thread_comments(
    thread_id: str, initial_block: Optional[dict]
) -> list[dict]:
    if not thread_id:
        return []
    comments_block = initial_block or {}
    results = list(comments_block.get("nodes") or [])
    page_info = comments_block.get("pageInfo") or {}
    cursor = page_info.get("endCursor")
    while page_info.get("hasNextPage"):
        data = gh_graphql(
            GATHER_THREAD_COMMENTS_QUERY, {"threadId": thread_id, "cursor": cursor}
        )
        comments = ((data.get("data") or {}).get("node") or {}).get("comments") or {}
        extra_nodes = comments.get("nodes") or []
        results.extend(extra_nodes)
        page_info = comments.get("pageInfo") or {}
        cursor = page_info.get("endCursor")
    return results


def get_unresolved_feedback(
    owner_repo: str, pr_number: int, commit_sha: Optional[str] = None
) -> list[dict]:
    owner, name = _parse_owner_repo(owner_repo)
    threads: list[dict] = []
    cursor: Optional[str] = None
    while True:
        data = gh_graphql(
            REVIEW_THREADS_QUERY,
            {"owner": owner, "name": name, "number": pr_number, "cursor": cursor},
        )
        review_threads = (
            ((data.get("data") or {}).get("repository") or {}).get("pullRequest") or {}
        ).get("reviewThreads") or {}
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
            comment_commit = (
                commit_info.get("oid") if isinstance(commit_info, dict) else None
            )
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


def reply_to_review_comment(
    owner: str, name: str, pr_number: int, comment_id: int, body: str
) -> None:
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
            capture=False,
            timeout=30,
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
        run_cmd(
            ["gh", "api", "graphql", "--input", "-"],
            stdin=payload,
            capture=False,
            timeout=30,
        )

    call_with_backoff(action)


def acknowledge_review_items(
    owner_repo: str, pr_number: int, items: list[dict], processed_ids: Set[int]
) -> Set[int]:
    """Reply to review items, mutating and returning the processed ID set.

    Tests can pass a pre-seeded ``processed_ids`` instance to maintain
    deterministic behaviour without relying on package-level globals. The same
    set instance is returned for chaining convenience.
    """
    owner, name = _parse_owner_repo(owner_repo)
    for item in items:
        comment_id = item.get("comment_id")
        thread_id = item.get("thread_id")
        if isinstance(comment_id, int):
            processed_ids.add(comment_id)
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


def _parse_iso8601(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except ValueError:
        logger.debug("Unable to parse datetime value: %s", value)
        return None


def _commit_timestamp(repo_root: Path, commit_sha: str) -> Optional[datetime]:
    try:
        stdout, _stderr, _code = run_cmd(
            ["git", "show", "-s", "--format=%cI", commit_sha],
            cwd=repo_root,
        )
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "Failed to read commit timestamp for %s: %s",
            commit_sha,
            extract_called_process_error_details(exc),
        )
        return None
    return _parse_iso8601(stdout.strip())


def _collect_commit_status_contexts(owner_repo: str, commit_sha: str) -> list[dict]:
    owner, name = _parse_owner_repo(owner_repo)
    try:
        data = gh_graphql(
            COMMIT_STATUS_ROLLUP_QUERY,
            {"owner": owner, "name": name, "oid": commit_sha},
        )
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "Failed to fetch status rollup for %s: %s",
            commit_sha,
            extract_called_process_error_details(exc),
        )
        return []
    nodes = (
        ((data.get("data") or {}).get("repository") or {}).get("object") or {}
    ).get("statusCheckRollup") or {}
    contexts = (nodes.get("contexts") or {}).get("nodes") or []
    results: list[dict] = []
    for raw in contexts:
        if not isinstance(raw, dict):
            continue
        entry = {"__typename": raw.get("__typename")}
        if entry["__typename"] == "CheckRun":
            entry["name"] = raw.get("name")
            entry["state"] = raw.get("conclusion")
        elif entry["__typename"] == "StatusContext":
            entry["name"] = raw.get("context")
            entry["state"] = raw.get("state")
        else:
            entry["name"] = raw.get("name")
            entry["state"] = raw.get("state")
        results.append(entry)
    return results


def _recent_pr_activity(
    owner_repo: str, pr_number: int
) -> Tuple[list[dict], list[dict]]:
    owner, name = _parse_owner_repo(owner_repo)
    try:
        data = gh_graphql(
            PR_ACTIVITY_SNAPSHOT_QUERY,
            {"owner": owner, "name": name, "number": pr_number},
        )
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "Failed to fetch PR activity snapshot for #%s: %s",
            pr_number,
            extract_called_process_error_details(exc),
        )
        return [], []
    pr = (((data.get("data") or {}).get("repository") or {}).get("pullRequest")) or {}
    comments = (pr.get("comments") or {}).get("nodes") or []
    reviews = (pr.get("reviews") or {}).get("nodes") or []
    return comments, reviews


def should_stop_review_after_push(
    owner_repo: str, pr_number: int, commit_sha: Optional[str], repo_root: Path
) -> bool:
    if not commit_sha:
        return False
    commit_time = _commit_timestamp(repo_root, commit_sha)
    if not commit_time:
        return False

    contexts = _collect_commit_status_contexts(owner_repo, commit_sha)
    coderabbit_success = False
    for ctx in contexts:
        name = (ctx.get("name") or "").strip().lower()
        state = (ctx.get("state") or "").strip().upper()
        if not name:
            continue
        if "coderabbit" in name and state == "SUCCESS":
            coderabbit_success = True
            break
    if not coderabbit_success:
        return False

    comments, reviews = _recent_pr_activity(owner_repo, pr_number)
    coderabbit_activity_detected = False
    for comment in comments:
        login = (((comment.get("author") or {}).get("login")) or "").strip().lower()
        if login not in CODERABBIT_REVIEW_LOGINS:
            continue
        timestamp = _parse_iso8601(comment.get("createdAt"))
        if timestamp and timestamp >= commit_time:
            coderabbit_activity_detected = True
            break
    if coderabbit_activity_detected:
        return False

    copilot_ok = False
    for review in reviews:
        login = (((review.get("author") or {}).get("login")) or "").strip().lower()
        if login in CODERABBIT_REVIEW_LOGINS:
            timestamp = _parse_iso8601(review.get("submittedAt"))
            if timestamp and timestamp >= commit_time:
                coderabbit_activity_detected = True
                break
            continue
        if login not in COPILOT_REVIEW_LOGINS:
            continue
        timestamp = _parse_iso8601(review.get("submittedAt"))
        if not timestamp or timestamp < commit_time:
            continue
        body = (review.get("body") or "").strip()
        if body.endswith("generated no new comments."):
            copilot_ok = True
    if coderabbit_activity_detected or not copilot_ok:
        return False

    logger.info(
        "Stopping review loop for PR #%s: CodeRabbit succeeded without new comments and Copilot confirmed no new findings.",
        pr_number,
    )
    return True


def post_final_comment(
    pr_number: Optional[int],
    owner_repo: str,
    prd_path: Path,
    repo_root: Path,
    dry_run: bool = False,
) -> None:
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
            capture=False,
            timeout=60,
        )
        print(f"Posted final comment on PR #{pr_number}. Done.")
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "Failed to post final PR comment for #%s: %s",
            pr_number,
            extract_called_process_error_details(exc),
        )
