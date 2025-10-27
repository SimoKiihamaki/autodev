"""PR creation flow utilities."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from .command import run_cmd
from .gh_ops import get_pr_number_for_head
from .git_ops import git_push_branch
from .logging_utils import logger
from .policy import get_executor_policy, policy_runner
from .utils import extract_called_process_error_details, scrub_cli_text


def _format_troubleshooting(location: str, manual_step: str) -> str:
    return (
        "Troubleshooting guidance (common causes include authentication, network hiccups, "
        "branch protection rules, required status checks, or permissions):\n"
        f"  1. Review the error details {location} for specifics.\n"
        "  2. Verify authentication: `gh auth status` (re-authenticate with `gh auth login` if needed).\n"
        "  3. Confirm branch protection and required status checks permit the operation.\n"
        f"  4. {manual_step}"
    )


def _raise_push_error(exc: subprocess.CalledProcessError, branch: str, manual_location: str = "above") -> None:
    details = extract_called_process_error_details(exc)
    manual = f"Manually push the branch if necessary: `git push -u origin {branch}`"
    message = f"Failed to push branch '{branch}': {details}\n" + _format_troubleshooting(manual_location, manual)
    raise SystemExit(message) from exc


def _raise_pr_create_error(exc: subprocess.CalledProcessError, base_branch: str, new_branch: str) -> None:
    details = extract_called_process_error_details(exc)
    manual = f"Manually create the PR if necessary: `gh pr create --base {base_branch} --head {new_branch}`"
    message = (
        "Failed to create PR automatically via gh CLI.\n"
        + _format_troubleshooting("below", manual)
        + f"\n\ngh pr create error details:\n{details}\n"
    )
    raise SystemExit(message) from exc


def open_or_get_pr(
    new_branch: str,
    base_branch: str,
    repo_root: Path,
    prd_path: Path,
    codex_model: str,
    allow_unsafe_execution: bool,
    dry_run: bool,
    *,
    skip_runner: bool = False,
    already_pushed: bool = False,
) -> Optional[int]:
    pr_title_raw = f"Implement: {prd_path.name}"
    pr_body_raw = (
        f"Implements tasks from {prd_path} via automated executor (Codex/Claude) + CodeRabbit iterative loop."
    )
    pr_title = scrub_cli_text(pr_title_raw)
    pr_body = scrub_cli_text(pr_body_raw)

    print(f"\n=== Bot pushes branch and opens PR: {new_branch} -> {base_branch} ===")
    push_prompt = f"""
Prepare and push a PR for this branch:
- Ensure local QA passes (`make ci`).
- Commit any pending changes.
- Push '{new_branch}' to origin.
- Open a PR targeting '{base_branch}' with title {json.dumps(pr_title)} and body {json.dumps(pr_body)}.
- After success, print: PR_OPENED=YES
"""
    if dry_run:
        logger.info("Dry run enabled; skipping Codex PR creation routine for branch %s.", new_branch)
        return None

    push_performed = already_pushed

    if not skip_runner:
        pr_runner, _ = policy_runner(get_executor_policy(), phase="pr")

        result = pr_runner(
            push_prompt,
            repo_root,
            model=codex_model,
            enable_search=True,
            allow_unsafe_execution=allow_unsafe_execution,
        )
        if "PR_OPENED=YES" in (result or ""):
            push_performed = True
    else:
        print("Skipping executor-driven PR routine; using direct git commands.")
        if not already_pushed:
            try:
                git_push_branch(repo_root, new_branch)
                push_performed = True
            except subprocess.CalledProcessError as exc:
                _raise_push_error(exc, new_branch)

    pr_number = get_pr_number_for_head(new_branch, repo_root)
    if pr_number is None:
        out, _, _ = run_cmd(
            [
                "git",
                "rev-list",
                "--count",
                f"{base_branch}..{new_branch}",
            ],
            cwd=repo_root,
            timeout=30,
        )
        has_commits = False
        out_stripped = (out or "0").strip()
        try:
            has_commits = int(out_stripped or "0") > 0
        except ValueError:
            logger.warning("Could not parse commit count for %s..%s: %r", base_branch, new_branch, out_stripped)
        if not has_commits:
            print("Branch has no commits relative to base; skipping PR creation.")
            return None
        if not push_performed:
            try:
                git_push_branch(repo_root, new_branch)
                push_performed = True
            except subprocess.CalledProcessError as exc:
                _raise_push_error(exc, new_branch)
        try:
            out, _, _ = run_cmd(
                [
                    "gh",
                    "pr",
                    "create",
                    "--base",
                    base_branch,
                    "--head",
                    new_branch,
                    "--title",
                    pr_title,
                    "--body",
                    pr_body,
                    "--json",
                    "number",
                    "--jq",
                    ".number",
                ],
                cwd=repo_root,
                timeout=60,
            )
            num_text = out.strip()
            if num_text:
                try:
                    pr_number = int(num_text)
                except ValueError:
                    logger.warning("Unexpected PR number format: %r", num_text)
                    pr_number = None
        except subprocess.CalledProcessError as exc:
            details = extract_called_process_error_details(exc)
            if "No commits between" in details:
                print("GitHub refused to create a PR because the branch matches the base branch.")
                return None
            _raise_pr_create_error(exc, base_branch, new_branch)
        if pr_number is None:
            pr_number = get_pr_number_for_head(new_branch, repo_root)
    if pr_number is not None:
        print(f"Opened PR #{pr_number}")
    else:
        print("No PR opened.")

    return pr_number
