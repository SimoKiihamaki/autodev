"""Git-related helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .command import run_cmd
from .logging_utils import logger


PARSE_OWNER_REPO_ERROR = "Cannot parse owner/repo from: {}"


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
        logger.warning("Remote URL %s contains extra path segments; using %s/%s", url, parts[-2], parts[-1])
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
    if not any(line.split(":")[0].strip() == "save-me-copilot" for line in out.splitlines() if ":" in line):
        alias_command = 'api --method POST /repos/$1/pulls/$2/requested_reviewers -f "reviewers[]=copilot-pull-request-reviewer[bot]"'
        try:
            run_cmd([
                "gh",
                "alias",
                "set",
                "save-me-copilot",
                alias_command,
            ])
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
    status_out, _, _ = run_cmd(["git", "status", "--porcelain"], cwd=repo_root)
    if not status_out.strip():
        return None
    _, _, _ = run_cmd([
        "git",
        "stash",
        "push",
        "--include-untracked",
        "-m",
        message,
    ], cwd=repo_root)
    selector_out, _, rc = run_cmd(["git", "stash", "list", "-n1", "--format=%gd"], cwd=repo_root, check=False)
    if rc == 0:
        selector = selector_out.strip() or "stash@{0}"
        return selector
    return "stash@{0}"


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


def _print_codex_effective_config(repo_root: Path) -> None:
    """Attempt to dump the effective Codex config using whichever syntax the CLI accepts."""
    commands = [
        ["codex", "config", "show", "--effective"],
        ["codex", "config", "--effective"],
    ]
    for args in commands:
        try:
            out, err, rc = run_cmd(args, cwd=repo_root, check=False)
        except FileNotFoundError:
            return
        payload = out.strip() or err.strip()
        if rc == 0:
            if payload:
                print(payload)
            return
        lowered = (payload or "").lower()
        if "unexpected argument" in lowered:
            continue
        logger.warning("codex config diagnostics failed via %s: %s", " ".join(args), payload or f"exit code {rc}")
        return
    print("codex config diagnostics skipped (CLI rejected show/--effective flags).")


def print_codex_diagnostics(repo_root: Path) -> None:
    from .agents import codex_exec

    print("\n=== Codex diagnostics ===")
    codex_available = True
    try:
        ver_out, ver_err, ver_rc = run_cmd(["codex", "--version"], cwd=repo_root, check=False)
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
    if codex_available:
        _print_codex_effective_config(repo_root)

    if not codex_available:
        return
    try:
        status_out = codex_exec("/status", repo_root, allow_unsafe_execution=True)
        if status_out.strip():
            print(status_out.strip())
    except (RuntimeError, subprocess.CalledProcessError, OSError, ValueError, PermissionError):
        logger.exception("codex /status failed")
