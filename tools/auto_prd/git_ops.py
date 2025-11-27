"""Git-related helpers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .command import run_cmd
from .constants import SAFE_ENV_VAR
from .logging_utils import logger


PARSE_OWNER_REPO_ERROR = "Cannot parse owner/repo from: {}"

# Transient network/git errors that are typically recoverable via retry
GIT_TRANSIENT_ERRORS = [
    "Connection reset by peer",
    "Could not resolve host",
    "the remote end hung up unexpectedly",
    "Unable to connect to",
    "unable to access",
    "SSL certificate problem",
    "Connection timed out",
    "Connection refused",
    "Couldn't connect to server",
    "RPC failed",
    "early EOF",
    "pack-objects died",
]

# Exit codes that indicate transient failures (128 = git fatal error, often network-related)
GIT_RETRY_EXIT_CODES = {128}


def git_root() -> Path:
    out, _, _ = run_cmd(["git", "rev-parse", "--show-toplevel"])
    return Path(out.strip())


def parse_owner_repo_from_git() -> str:
    """Return the owner/repo identifier for origin, handling SSH URLs with ports."""
    out, _, _ = run_cmd(["git", "remote", "get-url", "origin"])
    url = out.strip()
    if url.startswith("git@"):
        # Drop everything before the last colon so we support git@host:repo, git@host:port:repo,
        # and git@[ipv6-host]:repo forms without needing to special-case bracketed addresses.
        # Some tooling emits the non-standard git@host:port:repo variant; this approach keeps the
        # owner/repo suffix regardless of how many intermediate segments appear before it.
        remainder = url.rsplit(":", 1)[-1]
    else:
        parsed = urlparse(url)
        remainder = parsed.path.lstrip("/")
    if remainder.endswith(".git"):
        remainder = remainder[:-4]
    parts = [segment for segment in remainder.split("/") if segment]
    if len(parts) < 2:
        raise RuntimeError(PARSE_OWNER_REPO_ERROR.format(url))
    if len(parts) > 2:
        logger.warning(
            "Remote URL %s contains extra path segments; using %s/%s",
            url,
            parts[-2],
            parts[-1],
        )
    owner, repo = parts[-2], parts[-1]
    if not owner or not repo:
        raise RuntimeError(PARSE_OWNER_REPO_ERROR.format(url))
    return f"{owner}/{repo}"


def ensure_gh_alias() -> None:
    try:
        out, _, _ = run_cmd(["gh", "alias", "list"])
    except FileNotFoundError:
        logger.debug("gh CLI not available; skipping alias setup")
        return
    if not any(
        line.split(":")[0].strip() == "save-me-copilot"
        for line in out.splitlines()
        if ":" in line
    ):
        alias_command = 'api --method POST /repos/$1/pulls/$2/requested_reviewers -f "reviewers[]=copilot-pull-request-reviewer[bot]"'
        try:
            run_cmd(
                [
                    "gh",
                    "alias",
                    "set",
                    "save-me-copilot",
                    alias_command,
                ]
            )
        except FileNotFoundError:
            logger.debug("gh CLI not available during alias creation; skipping")


def workspace_has_changes(repo_root: Path) -> bool:
    out, _, _ = run_cmd(["git", "status", "--porcelain"], cwd=repo_root)
    return bool(out.strip())


def git_status_snapshot(repo_root: Path) -> tuple[str, ...]:
    out, _, _ = run_cmd(["git", "status", "--porcelain"], cwd=repo_root)
    return tuple(sorted(out.splitlines()))


def git_current_branch(repo_root: Path) -> str:
    out, _, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)
    return out.strip()


def git_head_sha(repo_root: Path) -> str:
    out, _, _ = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_root)
    return out.strip()


def git_branch_exists(repo_root: Path, branch: str) -> bool:
    if not branch or not branch.strip():
        return False
    refs = [f"refs/heads/{branch}", f"refs/remotes/origin/{branch}"]
    for ref in refs:
        _, _, rc = run_cmd(
            ["git", "show-ref", "--verify", "--quiet", ref], cwd=repo_root, check=False
        )
        if rc == 0:
            return True
    return False


def git_default_branch(repo_root: Path) -> Optional[str]:
    out, _, rc = run_cmd(
        ["git", "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
        cwd=repo_root,
        check=False,
    )
    if rc == 0:
        ref = out.strip()
        if ref:
            return ref.rsplit("/", 1)[-1]
    out, _, rc = run_cmd(
        ["git", "config", "--get", "init.defaultBranch"], cwd=repo_root, check=False
    )
    if rc == 0:
        name = out.strip()
        if name:
            return name
    return None


def git_stash_worktree(repo_root: Path, message: str) -> Optional[str]:
    status_out, _, _ = run_cmd(["git", "status", "--porcelain"], cwd=repo_root)
    if not status_out.strip():
        return None
    _, _, _ = run_cmd(
        [
            "git",
            "stash",
            "push",
            "--include-untracked",
            "-m",
            message,
        ],
        cwd=repo_root,
    )
    selector_out, _, rc = run_cmd(
        ["git", "stash", "list", "-n1", "--format=%gd"], cwd=repo_root, check=False
    )
    if rc == 0:
        selector = selector_out.strip() or "stash@{0}"
        return selector
    return "stash@{0}"


def git_stash_pop(repo_root: Path, selector: str) -> None:
    run_cmd(["git", "stash", "pop", selector], cwd=repo_root)


class StashConflictError(Exception):
    """Raised when stash pop results in merge conflicts."""

    def __init__(self, message: str, conflicted_files: list[str], selector: str):
        super().__init__(message)
        self.conflicted_files = conflicted_files
        self.selector = selector


def safe_stash_pop(repo_root: Path, selector: str) -> None:
    """Pop stash with conflict detection and actionable recovery guidance.

    Args:
        repo_root: Repository root directory.
        selector: Stash selector (e.g., 'stash@{0}').

    Raises:
        StashConflictError: If stash pop results in merge conflicts.
        subprocess.CalledProcessError: For other git errors after retries.
    """
    try:
        git_stash_pop(repo_root, selector)
        return
    except subprocess.CalledProcessError as exc:
        # Decode stderr to check for conflict indicators
        stderr = ""
        if exc.stderr:
            if isinstance(exc.stderr, bytes):
                stderr = exc.stderr.decode("utf-8", errors="replace")
            else:
                stderr = str(exc.stderr)

        # Check for conflict indicators (git stash pop outputs "CONFLICT" in uppercase)
        conflict_indicators = [
            "CONFLICT",
            "Merge conflict",
        ]
        is_conflict = any(indicator in stderr for indicator in conflict_indicators)

        if is_conflict:
            # Get list of conflicted files
            status_out, _, _ = run_cmd(
                ["git", "status", "--porcelain"], cwd=repo_root, check=False
            )
            conflicted_files = []
            for line in status_out.splitlines():
                # UU = both modified (conflict), AA = both added, etc.
                if line.startswith(("UU", "AA", "DU", "UD", "AU", "UA")):
                    conflicted_files.append(line[3:].strip())

            recovery_msg = (
                f"Stash conflict detected when applying {selector}.\n"
                f"Conflicted files: {', '.join(conflicted_files) if conflicted_files else 'unknown'}\n\n"
                f"To resolve manually:\n"
                f"  cd {repo_root}\n"
                f"  git status                          # View conflict status\n"
                f"  git stash show -p {selector}        # View stash contents\n"
                f"  # Edit conflicted files to resolve\n"
                f"  git add <resolved files>\n"
                f"  git stash drop {selector}           # After resolving"
            )
            raise StashConflictError(recovery_msg, conflicted_files, selector) from exc

        # For non-conflict errors, re-raise the original exception
        raise


def git_stage_all(repo_root: Path) -> None:
    run_cmd(["git", "add", "-A"], cwd=repo_root)


def git_add(repo_root: Path, file_path: Path) -> None:
    """Stage a specific file for commit.

    Args:
        repo_root: Repository root directory.
        file_path: Path to the file to stage (can be relative or absolute).
    """
    run_cmd(["git", "add", "--", str(file_path)], cwd=repo_root)


def git_has_staged_changes(repo_root: Path) -> bool:
    _, _, rc = run_cmd(
        ["git", "diff", "--cached", "--quiet"], cwd=repo_root, check=False
    )
    return rc != 0


def git_commit(repo_root: Path, message: str) -> None:
    run_cmd(["git", "commit", "-m", message], cwd=repo_root)


def git_push_branch(repo_root: Path, branch: str, retries: int = 3) -> None:
    """Push branch to origin with retry for transient network failures.

    Args:
        repo_root: Repository root directory.
        branch: Branch name to push.
        retries: Number of retry attempts for transient failures.
    """
    run_cmd(
        ["git", "push", "-u", "origin", branch],
        cwd=repo_root,
        retries=retries,
        retry_on_codes=GIT_RETRY_EXIT_CODES,
        retry_on_stderr=GIT_TRANSIENT_ERRORS,
        backoff_base=2.0,
    )


def git_fetch_with_retry(
    repo_root: Path, remote: str = "origin", retries: int = 3
) -> None:
    """Fetch from remote with retry for transient network failures.

    Args:
        repo_root: Repository root directory.
        remote: Remote name to fetch from.
        retries: Number of retry attempts for transient failures.
    """
    run_cmd(
        ["git", "fetch", remote],
        cwd=repo_root,
        retries=retries,
        retry_on_codes=GIT_RETRY_EXIT_CODES,
        retry_on_stderr=GIT_TRANSIENT_ERRORS,
        backoff_base=2.0,
    )


def git_pull_with_retry(
    repo_root: Path,
    remote: str = "origin",
    branch: Optional[str] = None,
    retries: int = 3,
) -> None:
    """Pull from remote with retry for transient network failures.

    Args:
        repo_root: Repository root directory.
        remote: Remote name to pull from.
        branch: Branch to pull (uses current branch if None).
        retries: Number of retry attempts for transient failures.
    """
    cmd = ["git", "pull", remote]
    if branch:
        cmd.append(branch)
    run_cmd(
        cmd,
        cwd=repo_root,
        retries=retries,
        retry_on_codes=GIT_RETRY_EXIT_CODES,
        retry_on_stderr=GIT_TRANSIENT_ERRORS,
        backoff_base=2.0,
    )


def print_codex_diagnostics(repo_root: Path) -> None:
    from .agents import codex_exec

    print("\n=== Codex diagnostics ===")
    codex_available = True
    try:
        ver_out, ver_err, ver_rc = run_cmd(
            ["codex", "--version"], cwd=repo_root, check=False
        )
        if ver_rc == 0:
            payload = ver_out.strip() or ver_err.strip()
            if payload:
                print(payload)
        else:
            details = ver_err.strip() or ver_out.strip() or f"exit code {ver_rc}"
            print(f"codex --version exited with {ver_rc}: {details}")
    except FileNotFoundError:
        print("codex CLI unavailable; install it to enable diagnostics.")
        codex_available = False
    except (subprocess.CalledProcessError, OSError, ValueError):
        logger.exception("codex --version failed")

    if not codex_available:
        return
    if os.environ.get(SAFE_ENV_VAR) != "1":
        print(f"codex /status skipped (set {SAFE_ENV_VAR}=1 to enable).")
        return
    try:
        status_out = codex_exec("/status", repo_root, allow_unsafe_execution=True)
        if status_out.strip():
            print(status_out.strip())
    except (
        RuntimeError,
        subprocess.CalledProcessError,
        OSError,
        ValueError,
        PermissionError,
    ):
        logger.exception("codex /status failed")
