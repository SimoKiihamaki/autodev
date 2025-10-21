"""Git-related helpers."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .command import run_cmd
from .logging_utils import logger


def git_root() -> Path:
    out, _, _ = run_cmd(["git", "rev-parse", "--show-toplevel"])
    return Path(out.strip())


def parse_owner_repo_from_git() -> str:
    out, _, _ = run_cmd(["git", "remote", "get-url", "origin"])
    url = out.strip()
    if url.startswith("git@"):
        _, remainder = url.split(":", 1)
    else:
        parsed = urlparse(url)
        remainder = parsed.path.lstrip("/")
    if remainder.endswith(".git"):
        remainder = remainder[:-4]
    parts = remainder.split("/")
    if len(parts) < 2:
        raise RuntimeError(f"Cannot parse owner/repo from: {url}")
    owner, repo = parts[0], parts[1]
    if not owner or not repo:
        raise RuntimeError(f"Cannot parse owner/repo from: {url}")
    return f"{owner}/{repo}"


def ensure_gh_alias() -> None:
    out, _, _ = run_cmd(["gh", "alias", "list"])
    if "save-me-copilot" not in out:
        run_cmd(
            [
                "gh",
                "alias",
                "set",
                "save-me-copilot",
                "api --method POST /repos/$1/pulls/$2/requested_reviewers -f reviewers[]=copilot-pull-request-reviewer[bot]",
            ]
        )


def workspace_has_changes(repo_root: Path) -> bool:
    out, _, _ = run_cmd(["git", "status", "--porcelain"], cwd=repo_root)
    return bool(out.strip())


def git_status_snapshot(repo_root: Path) -> tuple[str, ...]:
    out, _, _ = run_cmd(["git", "status", "--short"], cwd=repo_root)
    return tuple(out.splitlines())


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
        _, _, rc = run_cmd(["git", "show-ref", "--verify", "--quiet", ref], cwd=repo_root, check=False)
        if rc == 0:
            return True
    return False


def git_default_branch(repo_root: Path) -> Optional[str]:
    out, _, rc = run_cmd(["git", "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"], cwd=repo_root, check=False)
    if rc == 0:
        ref = out.strip()
        if ref:
            return ref.rsplit("/", 1)[-1]
    out, _, rc = run_cmd(["git", "config", "--get", "init.defaultBranch"], cwd=repo_root, check=False)
    if rc == 0:
        name = out.strip()
        if name:
            return name
    return None


def git_stash_worktree(repo_root: Path, message: str) -> Optional[str]:
    run_cmd(["git", "stash", "push", "--include-untracked", "-m", message], cwd=repo_root)
    out, _, _ = run_cmd(["git", "stash", "list"], cwd=repo_root)
    for line in out.splitlines():
        if message in line:
            ref = line.split(":", 1)[0].strip()
            if ref:
                return ref
    return None


def git_stash_pop(repo_root: Path, selector: str) -> None:
    run_cmd(["git", "stash", "pop", selector], cwd=repo_root)


def git_stage_all(repo_root: Path) -> None:
    run_cmd(["git", "add", "-A"], cwd=repo_root)


def git_has_staged_changes(repo_root: Path) -> bool:
    _, _, rc = run_cmd(["git", "diff", "--cached", "--quiet"], cwd=repo_root, check=False)
    return rc != 0


def git_commit(repo_root: Path, message: str) -> None:
    run_cmd(["git", "commit", "-m", message], cwd=repo_root)


def git_push_branch(repo_root: Path, branch: str) -> None:
    run_cmd(["git", "push", "-u", "origin", branch], cwd=repo_root)


def print_codex_diagnostics(repo_root: Path, codex_exec) -> None:
    print("\n=== Codex diagnostics ===")
    try:
        cfg_out, cfg_err, cfg_rc = run_cmd(["codex", "config", "show", "--effective"], cwd=repo_root, check=False)
        if cfg_rc != 0:
            details = cfg_err.strip() or cfg_out.strip() or f"exit code {cfg_rc}"
            print(f"codex config show --effective exited with {cfg_rc}: {details}")
        else:
            if cfg_out.strip():
                print(cfg_out.strip())
            if cfg_err.strip():
                print(cfg_err.strip())
    except FileNotFoundError:
        print("codex config show --effective unavailable (codex CLI may be outdated).")
    except (subprocess.CalledProcessError, OSError, ValueError) as exc:
        logger.exception("codex config show --effective failed", exc_info=exc)

    try:
        status_out = codex_exec("/status", repo_root)
        if status_out.strip():
            print(status_out.strip())
    except (RuntimeError, subprocess.CalledProcessError, OSError, ValueError, PermissionError) as exc:
        logger.exception("codex /status failed", exc_info=exc)
