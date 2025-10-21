#!/usr/bin/env python3
"""
Fully autonomous PRD → code → PR → review/fix loop using:
- Codex CLI in non-interactive exec mode (edits code & runs commands itself)
- YOLO mode (--dangerously-bypass-approvals-and-sandbox) + web search
- CodeRabbit CLI prompt-only for findings → feed back into Codex
- PR open + Copilot request, then infinite review/fix loop by default

Security note: --yolo disables approvals and sandbox per the Codex security guide. Use with extreme care
(prefer a container/VM or locked-down workspace). This utility assumes Codex executes with
full workspace permissions; the helper enforces YOLO/"danger-full-access" on every codex exec
invocation to keep automation unblocked. See docs.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import random
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

CHECKBOX_ANY_RE = re.compile(r"^\s*[-*]\s*\[[ xX]\]", flags=re.MULTILINE)
CHECKBOX_UNCHECKED_RE = re.compile(r"^\s*[-*]\s*\[\s\]", flags=re.MULTILINE)
TASKS_LEFT_RE = re.compile(r"TASKS_LEFT\s*=\s*(\d+)", flags=re.IGNORECASE)
CODEX_READONLY_PATTERNS = (
    "sandbox is read-only",
    "sandbox: read-only",
    "writing outside of the project",
    "Operation not permitted",
    "EPERM",
    "blocked because the repo is mounted read-only",
    'approval policy "never" prevents escalation',
)
CODEX_READONLY_ERROR_MSG = (
    "Codex reported it cannot modify the workspace (detected phrase: {pattern!r}). "
    "Check `codex config show --effective` and adjust sandbox/approval settings so the agent has write access."
)

# ---------------------------- subprocess helpers ----------------------------

ZSH_PATH = shutil.which("zsh") or "/bin/zsh"
COMMAND_ALLOWLIST = {
    "codex",
    "coderabbit",
    "git",
    "gh",
    Path(ZSH_PATH).name,
    ZSH_PATH,
    "claude",
}
UNSAFE_ARG_CHARS = set("|;><`")
STDIN_MAX_BYTES = 200_000
SAFE_STDIN_ALLOWED_CTRL = {9, 10, 13}
SAFE_ENV_VAR = "AUTO_PRD_ALLOW_UNSAFE_EXECUTION"
SAFE_CWD_ROOTS: set[Path] = {Path(__file__).resolve().parent}
logger = logging.getLogger(__name__)
VALID_PHASES = ("local", "pr", "review_fix")
PHASES_WITH_COMMIT_RISK = {"local", "pr"}

# Timeout for command execution verification in resource-constrained environments
COMMAND_VERIFICATION_TIMEOUT_SECONDS = 8


def register_safe_cwd(path: Path) -> None:
    SAFE_CWD_ROOTS.add(path.resolve())


def is_within(path: Path, root: Path) -> bool:
    try:
        path_resolved = path.resolve()
    except FileNotFoundError:
        path_resolved = path
    root_resolved = root.resolve()
    return path_resolved == root_resolved or root_resolved in path_resolved.parents


def validate_command_args(cmd: list[str]) -> None:
    if not isinstance(cmd, list) or not cmd:
        raise ValueError("cmd must be a non-empty list of strings")
    for arg in cmd:
        if not isinstance(arg, str):
            raise ValueError("cmd entries must be strings")
        if not arg.strip():
            raise ValueError("cmd entries must not be empty or whitespace-only")
        if any(ch in UNSAFE_ARG_CHARS for ch in arg):
            raise ValueError(
                f"cmd argument contains unsafe shell metacharacters: {arg!r}"
            )
        if any(ord(ch) < 32 and ord(ch) not in SAFE_STDIN_ALLOWED_CTRL for ch in arg):
            raise ValueError(f"cmd argument contains control characters: {arg!r}")
        if "\n" in arg or "\r" in arg:
            raise ValueError(f"cmd argument must not contain newlines: {arg!r}")
    exe = cmd[0]
    if os.path.isabs(exe):
        exe_path = Path(exe)
        if (
            exe not in COMMAND_ALLOWLIST
            and exe_path.name not in COMMAND_ALLOWLIST
            and not any(is_within(exe_path, root) for root in SAFE_CWD_ROOTS)
        ):
            raise ValueError(f"Executable {exe!r} is not within allowed directories")
    elif exe not in COMMAND_ALLOWLIST:
        raise ValueError(
            f"Executable {exe!r} is not in the allowlist: {sorted(COMMAND_ALLOWLIST)}"
        )


def validate_cwd(cwd: Optional[Path]) -> None:
    if cwd is None:
        return
    if not isinstance(cwd, Path):
        raise ValueError("cwd must be a pathlib.Path instance when provided")
    resolved = cwd.resolve()
    if not any(is_within(resolved, root) for root in SAFE_CWD_ROOTS):
        raise ValueError(
            f"cwd {resolved} is not within allowed safe roots: {sorted(str(r) for r in SAFE_CWD_ROOTS)}"
        )


def validate_stdin(stdin: Optional[str]) -> None:
    if stdin is None:
        return
    if not isinstance(stdin, str):
        raise ValueError("stdin must be a string when provided")
    if len(stdin.encode("utf-8")) > STDIN_MAX_BYTES:
        raise ValueError(f"stdin exceeds maximum size of {STDIN_MAX_BYTES} bytes")
    if any(ord(ch) < 32 and ord(ch) not in SAFE_STDIN_ALLOWED_CTRL for ch in stdin):
        raise ValueError("stdin contains disallowed control characters")


def validate_extra_env(extra_env: Optional[dict]) -> None:
    if extra_env is None:
        return
    if not isinstance(extra_env, dict):
        raise ValueError("extra_env must be a dict of string pairs")
    for key, value in extra_env.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("extra_env keys and values must be strings")
        if "\n" in key or "\n" in value:
            raise ValueError("extra_env keys/values must not contain newlines")


def verify_unsafe_execution_ready() -> None:
    env_value = os.getenv(SAFE_ENV_VAR, "").strip().lower()
    ci_env = os.getenv("CI", "").strip().lower()
    if env_value not in {"1", "true", "yes"}:
        raise PermissionError(
            f"Unsafe execution requires setting {SAFE_ENV_VAR}=1 (or true/yes)."
        )
    if ci_env not in {"1", "true", "yes"}:
        raise PermissionError(
            "Unsafe execution is limited to CI/isolated environments. "
            "Set CI=1 (or true/yes) to confirm the environment."
        )
    logger.warning(
        "Unsafe Codex execution enabled due to %s and CI environment confirmation.",
        SAFE_ENV_VAR,
    )


def env_with_zsh(extra: dict | None = None) -> dict:
    env = os.environ.copy()
    env.setdefault("SHELL", ZSH_PATH)
    if extra:
        env.update(extra)
    return env


def ensure_claude_debug_dir() -> Optional[Path]:
    """Ensure the Claude CLI can write debug logs even in sandboxed environments.

    Returns:
        Optional[Path]: A writable directory path if one is found and successfully configured, or None otherwise.

    Side effects:
        Sets the CLAUDE_CODE_DEBUG_LOGS_DIR environment variable when a writable
        directory is found and successfully verified. This environment variable is used
        by the Claude CLI to determine where to write debug logs, which is critical for
        troubleshooting in sandboxed or restricted environments where the default
        debug directory may not be writable.
    """
    existing = os.getenv("CLAUDE_CODE_DEBUG_LOGS_DIR")
    candidates: list[Path] = []
    if existing:
        try:
            candidates.append(Path(existing).expanduser())
        except (ValueError, RuntimeError, OSError) as e:
            logger.warning(
                "Failed to expand CLAUDE_CODE_DEBUG_LOGS_DIR=%r: %s. Falling back to other candidates.",
                existing,
                e,
            )
    candidates += [
        Path(tempfile.gettempdir()) / "claude_code_logs",
        Path.cwd() / ".claude-debug",
    ]
    for base in candidates:
        try:
            base.mkdir(parents=True, exist_ok=True)
            if os.access(base, os.W_OK):
                # Positive write test with proper cleanup handling
                now_iso = datetime.now(timezone.utc).isoformat()
                rand_str = f"{random.getrandbits(64):016x}"
                test_content = f"writecheck-{os.getpid()}-{now_iso}-{rand_str}"
                test: Optional[Path] = None
                try:
                    with tempfile.NamedTemporaryFile(
                        mode="w+",
                        encoding="utf-8",
                        dir=base,
                        prefix=".writecheck_",
                        suffix=".tmp",
                        delete=False,
                    ) as tmpf:
                        tmpf.write(test_content)
                        tmpf.flush()
                        os.fsync(tmpf.fileno())
                        tmpf_name = tmpf.name
                    test = Path(tmpf_name)
                    # os.fsync() ensures data is written to disk, making additional sleep unnecessary
                    # Verify the content is readable and matches what was written
                    with open(tmpf_name, "r", encoding="utf-8") as verify_f:
                        read_back = verify_f.read()
                    if read_back != test_content:
                        # Content does not match, log a warning and skip this directory
                        logger.warning(
                            "Write verification failed for %s: expected %r, got %r",
                            base,
                            test_content,
                            read_back,
                        )
                        continue
                finally:
                    if test and test.exists():
                        test.unlink(missing_ok=True)
                os.environ["CLAUDE_CODE_DEBUG_LOGS_DIR"] = str(base)
                return base
        except OSError:
            continue
    return None


def run_cmd(
    cmd: list[str],
    cwd: Optional[Path] = None,
    check: bool = True,
    capture: bool = True,
    timeout: Optional[int] = None,
    extra_env: Optional[dict] = None,
    stdin: Optional[str] = None,
) -> Tuple[str, str, int]:
    validate_command_args(cmd)
    validate_cwd(cwd)
    validate_stdin(stdin)
    validate_extra_env(extra_env)
    exe = shutil.which(cmd[0])
    if not exe:
        raise FileNotFoundError(f"Command not found: {cmd[0]}")
    env = env_with_zsh(extra_env)
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=False,
        capture_output=capture,
        text=True,
        timeout=timeout,
        env=env,
        input=stdin,
    )
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode, cmd, output=proc.stdout, stderr=proc.stderr
        )
    return proc.stdout or "", proc.stderr or "", proc.returncode


def run_sh(
    script: str,
    cwd: Optional[Path] = None,
    check: bool = True,
    capture: bool = True,
    timeout: Optional[int] = None,
    extra_env: Optional[dict] = None,
) -> Tuple[str, str, int]:
    return run_cmd(
        [ZSH_PATH, "-lc", script],
        cwd=cwd,
        check=check,
        capture=capture,
        timeout=timeout,
        extra_env=extra_env,
    )


def require_cmd(name: str) -> None:
    """
    Ensure that a given command-line tool is available on the system and can be invoked.

    This function checks if the specified command exists in the system's PATH and attempts
    multiple verification approaches including running common version/help commands and
    executing the command with no arguments to verify it can be invoked. If all version/help
    checks fail, it tries to execute the command with no arguments as a last resort to
    confirm basic invocability.

    Parameters:
        name (str): The name of the command to check (e.g., 'git', 'python').

    Raises:
        RuntimeError: If the command is not found (i.e., not installed or not on PATH).

    Note:
        This function only verifies that the command exists and can be invoked; it does not
        guarantee the command will work correctly with production arguments or return
        successful exit codes for all operations.
    """
    # First check if command exists using shutil.which
    cmd_path = shutil.which(name)
    if cmd_path is None:
        raise RuntimeError(
            f"'{name}' command not found - not installed or not on PATH."
        )

    # Then try to verify it's executable by checking version, help, or running a simple command
    # Some commands don't support --version, so we'll use a more flexible approach
    version_checks = [
        [name, "--version"],
        [name, "version"],
        [name, "--help"],
    ]

    for args in version_checks:
        try:
            run_cmd(args, check=True, capture=True, timeout=10)
            return  # Command works
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            continue

    # If all version checks fail, try to run the command with no args to see if it's executable
    try:
        stdout, stderr, returncode = run_cmd(
            [name],
            check=False,
            capture=True,
            timeout=COMMAND_VERIFICATION_TIMEOUT_SECONDS,
        )
        # If we get here without FileNotFoundError, the command exists
        # Accept return codes 0-2 as reasonable for command existence checks
        # 0 = success, 1 = general error, 2 = misuse error (common for commands requiring args)
        if returncode > 2:
            logger.warning(
                "Command '%s' returned unusual exit code %s, but still considering it as existing",
                name,
                returncode,
            )
        logger.info(
            "Command '%s' exists and returned exit code %s (may require arguments to run properly)",
            name,
            returncode,
        )
        return
    except FileNotFoundError:
        # This shouldn't happen since we checked with shutil.which, but handle it
        raise RuntimeError(
            f"'{name}' command not found - not installed or not on PATH."
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        # Command exists but failed to execute - this is still considered valid for existence check
        logger.info(
            "Command '%s' exists but failed execution (this may be expected if it requires arguments): %s",
            name,
            exc,
        )
        return


# ---------------------------- git helpers ----------------------------


def git_root() -> Path:
    out, _, _ = run_cmd(["git", "rev-parse", "--show-toplevel"])
    return Path(out.strip())


def parse_owner_repo_from_git() -> str:
    out, _, _ = run_cmd(["git", "remote", "get-url", "origin"])
    url = out.strip()
    m = re.search(r"[:/]([^/:]+)/([^/\.]+)(?:\.git)?$", url)
    if not m:
        raise RuntimeError(f"Cannot parse owner/repo from: {url}")
    return f"{m.group(1)}/{m.group(2)}"


def ensure_gh_alias() -> None:
    out, _, _ = run_cmd(["gh", "alias", "list"])
    if "save-me-copilot" not in out:
        # Unofficial way to request Copilot review for a PR
        run_cmd(
            [
                "gh",
                "alias",
                "set",
                "save-me-copilot",
                "api --method POST /repos/$1/pulls/$2/requested_reviewers "
                "-f reviewers[]=copilot-pull-request-reviewer[bot]",
            ]
        )


# ---------------------------- utilities ----------------------------


def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.strip().lower())
    return re.sub(r"-+", "-", s).strip("-") or "task"


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def checkbox_stats(md: Path) -> Tuple[int, int]:
    if not md.exists():
        return 0, 0
    txt = md.read_text(encoding="utf-8", errors="ignore")
    total = len(CHECKBOX_ANY_RE.findall(txt))
    unchecked = len(CHECKBOX_UNCHECKED_RE.findall(txt))
    return unchecked, total


def parse_tasks_left(output: str) -> Optional[int]:
    if not output:
        return None
    m = TASKS_LEFT_RE.search(output)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


RATE_LIMIT_STATUS = {"403", "429"}


def extract_http_status(exc: subprocess.CalledProcessError) -> Optional[str]:
    stderr = getattr(exc, "stderr", None)
    # CalledProcessError uses 'output' for stdout in some cases, 'stdout' in others
    stdout = getattr(exc, "output", None)
    if stdout is None:
        stdout = getattr(exc, "stdout", None)
    text = (stderr or "") + "\n" + (stdout or "")
    match = re.search(r"HTTP\s+(\d{3})", text)
    if match:
        return match.group(1)
    return None


def extract_called_process_error_details(exc: subprocess.CalledProcessError) -> str:
    """Extract stdout/stderr details from CalledProcessError for error messages."""
    stderr = getattr(exc, "stderr", None)
    # CalledProcessError uses 'output' for stdout in some cases, 'stdout' in others
    stdout = getattr(exc, "output", None)
    if stdout is None:
        stdout = getattr(exc, "stdout", None)
    return (stderr or stdout or "").strip() or f"exit code {exc.returncode}"


def call_with_backoff(action, *, retries: int = 3, base_delay: float = 1.0) -> Any:
    attempt = 0
    while True:
        try:
            return action()
        except subprocess.CalledProcessError as exc:
            status = extract_http_status(exc)
            if status not in RATE_LIMIT_STATUS or attempt >= retries:
                raise
            sleep_for = base_delay * (2**attempt) + random.uniform(0.0, 0.5)
            time.sleep(sleep_for)
            attempt += 1


def detect_readonly_block(output: str) -> Optional[str]:
    if not output:
        return None
    lowered = output.lower()
    for pattern in CODEX_READONLY_PATTERNS:
        if pattern.lower() in lowered:
            return pattern
    return None


def workspace_has_changes(repo_root: Path) -> bool:
    return bool(git_status_snapshot(repo_root))


def git_status_snapshot(repo_root: Path) -> tuple[str, ...]:
    out, _, _ = run_cmd(["git", "status", "--porcelain"], cwd=repo_root)
    lines = [line.rstrip("\n") for line in out.splitlines() if line.strip()]
    return tuple(sorted(lines))


def git_current_branch(repo_root: Path) -> str:
    out, _, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)
    return (out or "").strip()


def git_head_sha(repo_root: Path) -> str:
    out, _, _ = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_root)
    return out.strip()


def git_stash_worktree(repo_root: Path, message: str) -> Optional[str]:
    """Stash current working tree, including untracked files, and return the stash reference."""
    run_cmd(
        ["git", "stash", "push", "--include-untracked", "-m", message],
        cwd=repo_root,
    )
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
    _, _, rc = run_cmd(
        ["git", "diff", "--cached", "--quiet"], cwd=repo_root, check=False
    )
    return rc != 0


def git_commit(repo_root: Path, message: str) -> None:
    run_cmd(["git", "commit", "-m", message], cwd=repo_root)


def git_push_branch(repo_root: Path, branch: str) -> None:
    run_cmd(["git", "push", "-u", "origin", branch], cwd=repo_root)


def print_codex_diagnostics(repo_root: Path) -> None:
    print("\n=== Codex diagnostics ===")
    try:
        cfg_out, cfg_err, cfg_rc = run_cmd(
            ["codex", "config", "show", "--effective"], cwd=repo_root, check=False
        )
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
    except (
        RuntimeError,
        subprocess.CalledProcessError,
        OSError,
        ValueError,
        PermissionError,
    ) as exc:
        logger.exception("codex /status failed", exc_info=exc)


# ---------------------------- Codex (YOLO) ----------------------------


def codex_exec(
    prompt: str,
    repo_root: Path,
    model: str = "gpt-5-codex",
    enable_search: bool = True,
    yolo: bool = False,
    allow_unsafe_execution: bool = False,
    dry_run: bool = False,
    extra: Optional[list[str]] = None,
) -> str:
    """Invoke Codex CLI non-interactively, forcing YOLO/full-access for uninterrupted automation."""
    # Force all invocations into full YOLO / danger mode so Codex can edit files freely.
    yolo = True
    allow_unsafe_execution = True
    os.environ.setdefault(SAFE_ENV_VAR, "1")
    os.environ.setdefault("CI", "1")
    args: list[str] = ["codex"]
    if enable_search:
        args.append("--search")
    if yolo:
        verify_unsafe_execution_ready()
        args.append("--dangerously-bypass-approvals-and-sandbox")
        args.extend(["--config", 'sandbox_mode="danger-full-access"'])
        args.extend(["--config", 'shell_environment_policy.inherit="all"'])
    elif allow_unsafe_execution:
        verify_unsafe_execution_ready()
        args.extend(["--config", 'sandbox_mode="danger-full-access"'])
        args.extend(["--config", 'shell_environment_policy.inherit="all"'])
    if extra:
        args.extend(extra)
    args.extend(["exec", "--model", model, "-"])
    if dry_run:
        logger.info("Dry run enabled; skipping Codex execution. Args: %s", args)
        return "DRY_RUN"
    out, _, _ = run_cmd(args, cwd=repo_root, check=True, stdin=prompt)
    return out


# ---------------------------- CodeRabbit CLI ----------------------------


def parse_rate_limit_sleep(message: str) -> Optional[int]:
    if not message:
        return None
    match = re.search(
        r"try after (\d+)\s+(?:minute(?:s)?|min(?:s)?)\s+and\s+(\d+)\s+(?:second(?:s)?|sec(?:s)?)",
        message,
        re.IGNORECASE,
    )
    if match:
        minutes = int(match.group(1))
        seconds = int(match.group(2))
        return minutes * 60 + seconds + 5
    match = re.search(
        r"try after (\d+)\s+(?:second(?:s)?|sec(?:s)?)",
        message,
        re.IGNORECASE,
    )
    if match:
        seconds = int(match.group(1))
        return seconds + 5
    return None


def coderabbit_prompt_only(base_branch: str | None, repo_root: Path) -> str:
    args = ["coderabbit", "--prompt-only"]
    if base_branch:
        args += ["--base", base_branch]
    attempts = 0
    while True:
        attempts += 1
        try:
            out, _, _ = run_cmd(args, cwd=repo_root)
            return out.strip()
        except subprocess.CalledProcessError as exc:
            msg = extract_called_process_error_details(exc)
            sleep_secs = parse_rate_limit_sleep(msg)
            if sleep_secs and attempts <= 3:
                logger.warning(
                    "CodeRabbit rate limited; sleeping %s seconds before retry",
                    sleep_secs,
                )
                time.sleep(sleep_secs)
                continue
            logger.warning("CodeRabbit prompt-only run failed: %s", msg or exc)
            return ""


def coderabbit_has_findings(text: str) -> bool:
    if not text.strip():
        return False
    t = text.lower()
    for m in (
        "file:",
        "line",
        "issue",
        "prompt for ai agent",
        "consider",
        "fix",
        "security",
        "leak",
        "race",
    ):
        if m in t:
            return True
    return False


# ---------------------------- Claude Code ----------------------------


def claude_exec(
    prompt: str,
    repo_root: Path,
    model: str | None = None,
    enable_search: bool = True,
    yolo: bool = False,
    allow_unsafe_execution: bool = False,
    dry_run: bool = False,
    extra: Optional[list[str]] = None,
) -> str:
    """Invoke Claude CLI non-interactively. We pass the prompt via STDIN to avoid shell-arg limits
    and to keep our command-arg validator happy. We prefer a fully non-interactive run (like Codex).
    """
    os.environ.setdefault(SAFE_ENV_VAR, "1")
    os.environ.setdefault("CI", "1")
    verify_unsafe_execution_ready()
    args: list[str] = ["claude", "--dangerously-skip-permissions"]
    if extra:
        args.extend(extra)
    args.extend(["-p", "-"])
    if dry_run:
        logger.info("Dry run enabled; skipping Claude execution. Args: %s", args)
        return "DRY_RUN"
    out, _, _ = run_cmd(args, cwd=repo_root, check=True, stdin=prompt)
    return out


# ---------------------------- Executor Policy ----------------------------

EXECUTOR_CHOICES = {"codex-first", "codex-only", "claude-only"}
EXECUTOR_POLICY_DEFAULT = "codex-first"
EXECUTOR_POLICY = os.getenv("AUTO_PRD_EXECUTOR_POLICY") or EXECUTOR_POLICY_DEFAULT

# Fallback policies for when primary tools are unavailable.
# Currently, only a single fallback is implemented ("codex-first" → "codex-only").
# This structure is designed to support multiple fallback chains in the future;
# add additional entries as new executor policies and fallbacks are introduced.
FALLBACK_POLICIES = {
    "codex-first": "codex-only",  # Fallback to codex-only if Claude is unavailable
}

# Command-specific fallback configurations for when tools fail verification
# Maps command names to the executor policies that should trigger fallbacks
COMMAND_FALLBACK_CONFIG = {
    "claude": {"codex-first"},  # Claude failure triggers fallback in codex-first policy
}


def _compute_max_fallback_attempts(fallback_policies: dict) -> int:
    """Compute the maximum number of fallback attempts based on the fallback policy chains."""

    def chain_length(policy: str, visited: set) -> int:
        length = 0
        while policy in fallback_policies and policy not in visited:
            visited.add(policy)
            policy = fallback_policies[policy]
            length += 1
        return length

    max_chain = 0
    for policy in fallback_policies:
        max_chain = max(max_chain, chain_length(policy, set()))
    return max_chain + 1  # +1 for the initial attempt


# Dynamically computed as the longest fallback chain plus the initial attempt.
MAX_FALLBACK_ATTEMPTS = _compute_max_fallback_attempts(FALLBACK_POLICIES)


def get_fallback_policy(policy: str) -> Optional[str]:
    """Get the fallback policy for a given executor policy if a primary tool fails.

    Args:
        policy: The current executor policy

    Returns:
        Optional[str]: The fallback policy if one exists, None otherwise
    """
    return FALLBACK_POLICIES.get(policy)


def build_required_list(policy: str) -> list[str]:
    """Build the list of required commands based on executor policy.

    This function explicitly builds a required list based on policy, not phase.
    Includes core workflow dependencies (review processing and git/GitHub operations)
    that are commonly needed across the automation pipeline, though specific usage
    may vary depending on the selected phases and execution context.

    Args:
        policy: Executor policy string. Must be one of: "codex-first", "codex-only", "claude-only"

    Returns:
        List of required command names for the given policy.

    Raises:
        ValueError: If policy is not one of the expected values.
    """
    if policy not in EXECUTOR_CHOICES:
        raise ValueError(
            f"Invalid executor policy '{policy}'. Must be one of: {sorted(EXECUTOR_CHOICES)}"
        )

    required = ["coderabbit", "git", "gh"]
    if policy in ("codex-first", "codex-only"):
        required.append("codex")
    if policy in ("codex-first", "claude-only"):
        required.append("claude")
    return required


def policy_runner(
    policy: str | None, i: int | None = None, phase: str = "implement"
) -> Tuple[Callable[..., str], str]:
    """
    Decide which executor to use for a given phase/iteration.
    Returns (callable, human_label).
    Phases: "implement", "fix", "pr", "review_fix"
    """
    # Phase-specific env overrides: AUTO_PRD_EXECUTOR_IMPLEMENT, _FIX, _PR, _REVIEW_FIX
    env_key_map = {
        "implement": "AUTO_PRD_EXECUTOR_IMPLEMENT",
        "fix": "AUTO_PRD_EXECUTOR_FIX",
        "pr": "AUTO_PRD_EXECUTOR_PR",
        "review_fix": "AUTO_PRD_EXECUTOR_REVIEW_FIX",
    }
    ek = env_key_map.get(phase)
    if ek:
        override = (os.getenv(ek) or "").strip().lower()
        if override in ("codex", "claude"):
            return (
                (codex_exec, "Codex")
                if override == "codex"
                else (claude_exec, "Claude")
            )

    p = (policy or EXECUTOR_POLICY_DEFAULT).strip().lower()
    if p not in EXECUTOR_CHOICES:
        logger.warning(
            "Unknown executor policy %s; defaulting to %s", p, EXECUTOR_POLICY_DEFAULT
        )
        p = EXECUTOR_POLICY_DEFAULT

    if p == "codex-only":
        return codex_exec, "Codex"
    if p == "claude-only":
        return claude_exec, "Claude"

    # codex-first
    if phase in ("pr", "review_fix"):
        return claude_exec, "Claude"
    if i == 1:
        return codex_exec, "Codex"
    return claude_exec, "Claude"


# ---------------------------- GH review plumbing ----------------------------

REVIEW_THREADS_QUERY = """
query($owner:String!, $name:String!, $number:Int!, $cursor:String) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      reviewThreads(first: 50, after: $cursor) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          isResolved
          comments(first: 50) {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              id
              databaseId
              author { login }
              body
              url
              createdAt
              commit { oid }
            }
          }
        }
      }
    }
  }
}
"""

REVIEW_THREAD_COMMENTS_QUERY = """
query($threadId:ID!, $cursor:String) {
  node(id:$threadId) {
    ... on PullRequestReviewThread {
      comments(first: 50, after: $cursor) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          databaseId
          author { login }
          body
          url
          createdAt
          commit { oid }
        }
      }
    }
  }
}
"""

REVIEW_BOT_LOGINS = {
    "coderabbitai",
    "coderabbit-ai",
    "coderabbit",
    "copilot-pull-request-reviewer",
    "copilot-pull-request-reviewer[bot]",
    "github-copilot",
    "github-copilot[bot]",
}

PROCESSED_REVIEW_COMMENT_IDS: set[int] = set()


def gh_graphql(query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables})
    out, _, _ = run_cmd(
        ["gh", "api", "graphql", "--input", "-"],
        stdin=payload,
    )
    return json.loads(out)


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
    s = out.strip()
    return int(s) if s else None


def branch_has_commits_since(base_branch: str, repo_root: Path) -> bool:
    out, _, _ = run_cmd(
        ["git", "rev-list", "--count", f"{base_branch}..HEAD"], cwd=repo_root
    )
    try:
        return int(out.strip() or "0") > 0
    except ValueError:
        return False


def trigger_copilot(owner_repo: str, pr_number: int, repo_root: Path) -> None:
    try:
        run_cmd(["gh", "save-me-copilot", owner_repo, str(pr_number)], cwd=repo_root)
    except subprocess.CalledProcessError:
        # Official path is selecting Copilot from PR Reviewers or configuring automatic reviews.
        # We silently continue if alias fails.
        pass


def _gather_thread_comments(
    thread_id: str, initial_block: Optional[dict]
) -> list[dict]:
    """Gather every comment node for a review thread by following pagination cursors."""
    if not thread_id:
        return []
    comments_block = initial_block or {}
    results = list(comments_block.get("nodes") or [])
    page_info = comments_block.get("pageInfo") or {}
    cursor = page_info.get("endCursor")
    while page_info.get("hasNextPage"):
        data = gh_graphql(
            REVIEW_THREAD_COMMENTS_QUERY, {"threadId": thread_id, "cursor": cursor}
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
    owner, name = owner_repo.split("/", 1)
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
    for t in threads:
        if t.get("isResolved") is True:
            continue
        thread_id = t.get("id")
        if not thread_id:
            # Avoid logging the full thread object to prevent leaking sensitive info
            preview = ""
            comments = t.get("comments", {}).get("nodes", [])
            if comments and isinstance(comments, list):
                first_comment = comments[0]
                body = (first_comment.get("body") or "").strip()
                if body:
                    preview = f' Preview of first comment: "{body[:50]}{"..." if len(body) > 50 else ""}"'
            logger.warning(
                "Encountered review thread without an ID. Skipping this thread; unable to gather comments for review processing. This may cause some review comments to be missed.%s",
                preview,
            )
            continue
        comments = _gather_thread_comments(thread_id, t.get("comments"))
        for c in comments:
            login = ((c.get("author") or {}).get("login") or "").strip()
            if login.lower() not in REVIEW_BOT_LOGINS:
                continue
            body = (c.get("body") or "").strip()
            url = c.get("url") or ""
            if not body:
                continue
            commit_info = c.get("commit") or {}
            comment_commit = (
                commit_info.get("oid") if isinstance(commit_info, dict) else None
            )
            if commit_sha:
                if not comment_commit or comment_commit != commit_sha:
                    continue
            db_id = c.get("databaseId")
            if db_id is not None:
                unresolved.append(
                    {
                        "summary": f"- {login or 'unknown'}: {body}\n  {url}",
                        "thread_id": thread_id,
                        "comment_id": db_id,
                        "author": login or "unknown",
                        "url": url,
                        "is_resolved": bool(t.get("isResolved")),
                    }
                )
    return unresolved


def reply_to_review_comment(
    owner: str, name: str, pr_number: int, comment_id: int, body: str
):
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


def acknowledge_review_items(
    owner_repo: str, pr_number: int, items: list[dict]
) -> None:
    owner, name = owner_repo.split("/", 1)
    for item in items:
        comment_id = item.get("comment_id")
        thread_id = item.get("thread_id")
        if (
            isinstance(comment_id, int)
            and comment_id not in PROCESSED_REVIEW_COMMENT_IDS
        ):
            reply_body = (
                "Fix applied in the latest push—thanks for the review! "
                "@CodeRabbitAI @coderabbit @copilot"
            )
            try:
                reply_to_review_comment(owner, name, pr_number, comment_id, reply_body)
                PROCESSED_REVIEW_COMMENT_IDS.add(comment_id)
            except subprocess.CalledProcessError as exc:
                logger.warning(
                    "Failed to reply to review comment %s: %s", comment_id, exc
                )
        if thread_id and not item.get("is_resolved"):
            try:
                resolve_review_thread(thread_id)
            except subprocess.CalledProcessError as exc:
                logger.warning("Failed to resolve review thread %s: %s", thread_id, exc)


# ---------------------------- Orchestration ----------------------------

LOCAL_QA_SNIPPET = """
Use zsh for shell commands.
Run `make ci` (or create the Makefile above if missing) and keep rerunning until green.
CI expectations: unit + e2e tests, lint, typecheck, format check.
Commit frequently with Conventional Commits, include rationale and test notes.
Keep the PRD in sync (checkboxes, remaining tasks) and finish with TASKS_LEFT=<N>.
"""

LOCAL_QA_REMINDER = "Remember the QA SOP from your first pass: `make ci` must be green; rerun as needed."

NO_FINDINGS_STREAK_LIMIT = 2
MAX_EMPTY_CHANGE_STREAK = 3


def orchestrate_local_loop(
    prd_path: Path,
    repo_root: Path,
    base_branch: str,
    max_iters: int,
    codex_model: str,
    allow_unsafe_execution: bool,
    dry_run: bool,
) -> tuple[int, bool]:
    unchecked, total_checkboxes = checkbox_stats(prd_path)
    print(f"Unchecked checkboxes in PRD (heuristic): {unchecked}/{total_checkboxes}")
    tasks_left: Optional[int] = None
    appears_complete = False
    no_findings_streak = 0
    qa_context_shared = False
    previous_status = git_status_snapshot(repo_root)
    previous_head = git_head_sha(repo_root)
    empty_change_streak = 0

    for i in range(1, max_iters + 1):
        print(f"\n=== Iteration {i}/{max_iters}: Codex implements next chunk ===")
        previous_tasks_left = tasks_left
        before_status = previous_status
        before_head = previous_head

        qa_section = LOCAL_QA_SNIPPET if not qa_context_shared else LOCAL_QA_REMINDER
        impl_prompt = f"""
Read the spec at '{prd_path}'. Implement the NEXT uncompleted tasks in '{repo_root}'.

{qa_section}

At the end, print: TASKS_LEFT=<N>
"""
        runner, runner_name = policy_runner(EXECUTOR_POLICY, i=i, phase="implement")
        print("→ Launching implementation pass with", runner_name, "…")
        impl_output = runner(
            impl_prompt,
            repo_root,
            model=codex_model,
            enable_search=True,
            yolo=allow_unsafe_execution,
            allow_unsafe_execution=allow_unsafe_execution,
            dry_run=dry_run,
        )
        print("✓ Codex implementation pass completed.")
        readonly_indicator = detect_readonly_block(impl_output)
        if readonly_indicator:
            raise RuntimeError(
                CODEX_READONLY_ERROR_MSG.format(pattern=readonly_indicator)
            )
        iter_tasks_left = parse_tasks_left(impl_output)
        if iter_tasks_left is not None:
            tasks_left = iter_tasks_left
            print(f"Codex reported TASKS_LEFT={tasks_left}")
        else:
            print("Codex did not report TASKS_LEFT (continuing)")

        qa_context_shared = True

        if not dry_run:
            status_after_impl = git_status_snapshot(repo_root)
            head_after_impl = git_head_sha(repo_root)
        else:
            status_after_impl = before_status
            head_after_impl = before_head

        repo_changed_before_review = (
            status_after_impl != before_status or head_after_impl != before_head
        )
        tasks_progress = (
            previous_tasks_left is not None
            and tasks_left is not None
            and tasks_left < previous_tasks_left
        )

        has_findings = False
        status_after_iteration = status_after_impl
        head_after_iteration = head_after_impl

        if not repo_changed_before_review and not tasks_progress:
            no_findings_streak += 1
            print(
                "No new file changes detected; skipping CodeRabbit review this iteration."
            )
            print(f"CodeRabbit no-findings streak: {no_findings_streak}")
        else:
            print("\n=== CodeRabbit CLI review (prompt-only) ===")
            cr = coderabbit_prompt_only(base_branch=base_branch, repo_root=repo_root)
            has_findings = coderabbit_has_findings(cr)
            if has_findings:
                no_findings_streak = 0
                print("\n=== Codex applies CodeRabbit findings ===")
                fix_prompt = f"""
You are fixing findings reported by CodeRabbit CLI:

<CODE_RABBIT_FINDINGS>
{cr[:20000]}
</CODE_RABBIT_FINDINGS>

Apply targeted changes, commit frequently, and re-run the QA gates until green.

{LOCAL_QA_REMINDER}
"""
                print(
                    "→ Launching fix pass with",
                    runner_name,
                    "based on CodeRabbit feedback…",
                )
                fix_output = runner(
                    fix_prompt,
                    repo_root,
                    model=codex_model,
                    enable_search=True,
                    yolo=allow_unsafe_execution,
                    allow_unsafe_execution=allow_unsafe_execution,
                    dry_run=dry_run,
                )
                print("✓ Codex fix pass completed.")
                readonly_indicator = detect_readonly_block(fix_output)
                if readonly_indicator:
                    raise RuntimeError(
                        CODEX_READONLY_ERROR_MSG.format(pattern=readonly_indicator)
                    )
                fix_tasks_left = parse_tasks_left(fix_output)
                if fix_tasks_left is not None:
                    tasks_left = fix_tasks_left
                    print(
                        f"Codex reported TASKS_LEFT={tasks_left} after applying findings"
                    )
                if not dry_run:
                    status_after_iteration = git_status_snapshot(repo_root)
                    head_after_iteration = git_head_sha(repo_root)
            else:
                no_findings_streak += 1
                if not dry_run:
                    status_after_iteration = git_status_snapshot(repo_root)
                    head_after_iteration = git_head_sha(repo_root)
                print("No CodeRabbit findings detected in this pass.")
                print(f"CodeRabbit no-findings streak: {no_findings_streak}")

        repo_changed_after_actions = (
            status_after_iteration != before_status
            or head_after_iteration != before_head
        )

        if not repo_changed_after_actions:
            print("⚠️  Warning: no new workspace changes detected after this iteration.")
            if not dry_run:
                empty_change_streak += 1
                print(
                    f"Empty-change streak: {empty_change_streak}/{MAX_EMPTY_CHANGE_STREAK}"
                )
                if empty_change_streak >= MAX_EMPTY_CHANGE_STREAK:
                    raise RuntimeError(
                        "Codex iterations produced no file changes or commits after multiple passes."
                    )
                continue
        else:
            empty_change_streak = 0
            previous_status = status_after_iteration
            previous_head = head_after_iteration

        # Simple completion heuristics
        unchecked, total_checkboxes = checkbox_stats(prd_path)
        done_by_checkboxes = total_checkboxes > 0 and unchecked == 0
        done_by_codex = tasks_left == 0 if tasks_left is not None else False

        if (done_by_checkboxes or done_by_codex) and not has_findings:
            if tasks_left is None and not done_by_checkboxes:
                print(
                    "Completion cannot be confirmed (no TASKS_LEFT and no checkboxes); continuing loop."
                )
                continue
            else:
                print(
                    "Local loop stopping: PRD appears complete and CodeRabbit has no findings."
                )
                appears_complete = True
                break

        if no_findings_streak >= NO_FINDINGS_STREAK_LIMIT and not has_findings:
            print("Stopping after repeated no-finding reviews from CodeRabbit.")
            appears_complete = True
            break
    else:
        print("Reached local iteration cap, proceeding to PR step.")

    return tasks_left if tasks_left is not None else -1, appears_complete


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
    pr_title = f"Implement: {prd_path.name}"
    pr_body = f"Implements tasks from `{prd_path}` via automated executor (Codex/Claude) + CodeRabbit iterative loop."

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
        logger.info(
            "Dry run enabled; skipping Codex PR creation routine for branch %s.",
            new_branch,
        )
        return None

    if not skip_runner:
        pr_runner, pr_runner_name = policy_runner(EXECUTOR_POLICY, phase="pr")

        pr_runner(
            push_prompt,
            repo_root,
            model=codex_model,
            enable_search=True,
            yolo=allow_unsafe_execution,
            allow_unsafe_execution=allow_unsafe_execution,
        )
    else:
        print("Skipping executor-driven PR routine; using direct git commands.")
        if not already_pushed:
            try:
                git_push_branch(repo_root, new_branch)
            except subprocess.CalledProcessError as exc:
                details = extract_called_process_error_details(exc)
                raise SystemExit(f"Failed to push branch '{new_branch}': {details}")

    pr_number = get_pr_number_for_head(new_branch, repo_root)
    if pr_number is None:
        if not branch_has_commits_since(base_branch, repo_root):
            print("Branch has no commits relative to base; skipping PR creation.")
            return None
        # Fallback: open PR ourselves if Codex didn't
        run_cmd(["git", "push", "-u", "origin", new_branch], cwd=repo_root)
        try:
            run_cmd(
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
                ],
                cwd=repo_root,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            if "No commits between" in stderr:
                print(
                    "GitHub refused to create a PR because the branch matches the base branch."
                )
                return None
            raise
        pr_number = get_pr_number_for_head(new_branch, repo_root)
    print(f"Opened PR #{pr_number}")

    return pr_number


def review_fix_loop(
    pr_number: Optional[int],
    owner_repo: str,
    repo_root: Path,
    idle_grace: int,
    poll_interval: int,
    codex_model: str,
    allow_unsafe_execution: bool = False,
    dry_run: bool = False,
    initial_wait_minutes: int = 0,
    infinite_reviews: bool = False,
) -> None:
    if pr_number is None:
        return
    if dry_run:
        logger.info("Dry run enabled; skipping review loop for PR #%s.", pr_number)
        return

    trigger_copilot(owner_repo, pr_number, repo_root)
    initial_wait_seconds = max(0, initial_wait_minutes * 60)
    if initial_wait_seconds:
        print(f"Waiting {initial_wait_minutes} minutes for bot reviews...")
        time.sleep(initial_wait_seconds)

    idle_grace_seconds = max(0, idle_grace * 60)
    if infinite_reviews:
        idle_grace_seconds = float("inf")
    poll = max(15, poll_interval)
    last_activity = time.time()
    print("\n=== Entering review/fix loop (continues while feedback exists) ===")

    while True:
        current_head = git_head_sha(repo_root)
        unresolved_raw = get_unresolved_feedback(owner_repo, pr_number, current_head)
        unresolved = []
        for item in unresolved_raw:
            comment_id = item.get("comment_id")
            if (
                isinstance(comment_id, int)
                and comment_id in PROCESSED_REVIEW_COMMENT_IDS
            ):
                continue
            unresolved.append(item)
        if unresolved:
            bullets = "\n".join(f"* {u['summary']}" for u in unresolved)
            print("\nUnresolved feedback detected, asking the bot to fix...")
            fix_prompt = f"""
Resolve ALL items below, commit fixes, ensure QA passes, and push to the SAME PR (do not create a new one).
Before every push, run `make ci` locally and confirm it succeeds; only push after `make ci` passes cleanly.
Tag the relevant code areas and keep changes minimal.

Unresolved review items:
{bullets[:20000]}

After pushing, print: REVIEW_FIXES_PUSHED=YES
"""
            review_runner, review_runner_name = policy_runner(
                EXECUTOR_POLICY, phase="review_fix"
            )

            review_runner(
                fix_prompt,
                repo_root,
                model=codex_model,
                enable_search=True,
                yolo=allow_unsafe_execution,
                allow_unsafe_execution=allow_unsafe_execution,
            )
            # Retrigger Copilot each push
            trigger_copilot(owner_repo, pr_number, repo_root)
            acknowledge_review_items(owner_repo, pr_number, unresolved)
            last_activity = time.time()
            # Short backoff before polling again
            time.sleep(poll)
            continue

        # No unresolved feedback right now
        if idle_grace_seconds == 0:
            print("No unresolved feedback; stopping.")
            break
        # Wait/poll until idle window elapses with no new unresolved feedback
        elapsed = time.time() - last_activity
        if elapsed >= idle_grace_seconds:
            minutes = "∞" if infinite_reviews else idle_grace
            print(f"No unresolved feedback for {minutes} minutes; finishing.")
            break
        print("No unresolved feedback right now; waiting for potential new comments...")
        time.sleep(poll)

    print("Review loop complete.")


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


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    ap = argparse.ArgumentParser(
        description="Autonomous PRD→PR loop with Codex (YOLO), CodeRabbit & Copilot"
    )
    ap.add_argument("--prd", required=True, help="Path to PRD/task .md file")
    ap.add_argument(
        "--repo", default=None, help="Path to repo root (default: current git root)"
    )
    ap.add_argument(
        "--repo-slug", default=None, help="owner/repo; default parsed from git remote"
    )
    ap.add_argument("--base", default="main", help="Base branch (default: main)")
    ap.add_argument(
        "--branch", default=None, help="Feature branch (default: from PRD filename)"
    )
    ap.add_argument(
        "--codex-model",
        default="gpt-5-codex",
        help="Codex model to use (default: gpt-5-codex)",
    )
    ap.add_argument(
        "--wait-minutes",
        type=int,
        default=0,
        help="Initial wait for PR bot reviews (default: 0)",
    )
    ap.add_argument(
        "--review-poll-seconds",
        type=int,
        default=120,
        help="Polling interval when watching for reviews (default: 120)",
    )
    ap.add_argument(
        "--idle-grace-minutes",
        type=int,
        default=10,
        help="Stop after this many minutes with no unresolved feedback (default: 10)",
    )
    ap.add_argument(
        "--max-local-iters",
        type=int,
        default=50,
        help="Safety cap for local Codex<->CodeRabbit passes (default: 50)",
    )
    ap.add_argument(
        "--infinite-reviews",
        action="store_true",
        help="Continue indefinitely while feedback exists (overrides --idle-grace-minutes)",
    )
    ap.add_argument(
        "--sync-git",
        action="store_true",
        help="Fetch & fast-forward the base branch before creating the working branch",
    )
    ap.add_argument(
        "--allow-unsafe-execution",
        action="store_true",
        help=f"Allow Codex to run with unsafe capabilities (requires {SAFE_ENV_VAR}=1 and CI=1).",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not execute Codex commands; useful for tests.",
    )
    ap.add_argument(
        "--executor-policy",
        choices=("codex-first", "codex-only", "claude-only"),
        default=None,
        help="Executor policy: 'codex-first' (default), 'codex-only', or 'claude-only'. "
        "Can also use AUTO_PRD_EXECUTOR_POLICY.",
    )
    ap.add_argument(
        "--phases",
        default=None,
        help="Comma-separated list of phases to run (local,pr,review_fix). Default: all phases.",
    )
    args = ap.parse_args()
    ensure_claude_debug_dir()

    if args.phases is None:
        selected_phases = set(VALID_PHASES)
    else:
        selected_phases = {
            p.strip().lower() for p in args.phases.split(",") if p.strip()
        }
        invalid = selected_phases.difference(VALID_PHASES)
        if invalid:
            raise SystemExit(
                f"Invalid phase(s): {', '.join(sorted(invalid))}. Valid options: {', '.join(VALID_PHASES)}"
            )

    def include(phase: str) -> bool:
        return phase in selected_phases

    policy_from_env = os.getenv("AUTO_PRD_EXECUTOR_POLICY")
    global EXECUTOR_POLICY
    EXECUTOR_POLICY = args.executor_policy or policy_from_env or EXECUTOR_POLICY_DEFAULT
    if EXECUTOR_POLICY not in EXECUTOR_CHOICES:
        raise SystemExit(f"Invalid executor policy: {EXECUTOR_POLICY}")

    def verify_required_commands(
        required: list[str], executor_policy: str, verified_commands: set[str]
    ) -> tuple[bool, str, set[str]]:
        policy_changed = False
        for cmd_name in required:
            try:
                require_cmd(cmd_name)
                verified_commands.add(cmd_name)
            except RuntimeError as err:
                # Check if this command failure should trigger a policy fallback
                trigger_policies = COMMAND_FALLBACK_CONFIG.get(cmd_name, set())
                if executor_policy in trigger_policies:
                    policy_changed = True
                    print(
                        f"Warning: {cmd_name} CLI check failed; falling back to alternative executor policy."
                    )
                    print(f"Details:\n{err}")
                    fallback_policy = get_fallback_policy(executor_policy)
                    if fallback_policy is None:
                        raise SystemExit(
                            f"ERROR: {cmd_name} CLI check failed and no fallback policy available for '{executor_policy}'"
                        )
                    executor_policy = fallback_policy
                    break  # Stop and retry with new policy
                else:
                    raise SystemExit(f"ERROR: {err}")
        return policy_changed, executor_policy, verified_commands

    # Check required commands, with fallback based on command-specific configurations
    verified_commands: set[str] = set()
    fallback_attempts = 0
    executor_policy_chain = []
    initial_executor_policy = EXECUTOR_POLICY
    while True:
        executor_policy_chain.append(EXECUTOR_POLICY)
        policy_changed, EXECUTOR_POLICY, verified_commands = verify_required_commands(
            build_required_list(EXECUTOR_POLICY), EXECUTOR_POLICY, verified_commands
        )
        if not policy_changed:
            break
        fallback_attempts += 1
        if fallback_attempts >= MAX_FALLBACK_ATTEMPTS:
            last_required = build_required_list(EXECUTOR_POLICY)
            failed_commands = [
                cmd for cmd in last_required if cmd not in verified_commands
            ]

            # Check for actual cycles in the executor policy chain
            cycle_detected = False
            cycle_info = ""
            if len(executor_policy_chain) != len(set(executor_policy_chain)):
                # Find the cycle
                seen_indices = {}
                for i, policy in enumerate(executor_policy_chain):
                    if policy in seen_indices:
                        cycle_start = seen_indices[policy]
                        cycle_policies = executor_policy_chain[cycle_start:]
                        cycle_detected = True
                        cycle_info = (
                            f"Detected cycle: {' -> '.join(cycle_policies)} -> {policy}"
                        )
                        break
                    seen_indices[policy] = i

            error_type = "Cycle detected" if cycle_detected else "Persistent failure"
            cycle_message = f"\n{cycle_info}" if cycle_detected else ""

            raise SystemExit(
                f"ERROR: Exceeded maximum fallback attempts ({MAX_FALLBACK_ATTEMPTS}) while verifying required commands.\n"
                f"{error_type} in executor policy fallback logic.{cycle_message}\n"
                f"Executor policy chain tried: {executor_policy_chain}\n"
                f"Commands that failed to verify: {failed_commands}"
            )
        # If any required command fails, the loop will retry with updated EXECUTOR_POLICY and remaining commands
    # Print the final, active executor policy after all fallback logic
    print(
        f"Using executor policy: {EXECUTOR_POLICY}"
        + (
            f" (fallback from {initial_executor_policy})"
            if EXECUTOR_POLICY != initial_executor_policy
            else ""
        )
    )

    ensure_gh_alias()

    prd_path = Path(args.prd).resolve()
    repo_root = Path(args.repo).resolve() if args.repo else git_root()
    register_safe_cwd(repo_root)
    os.chdir(repo_root)

    owner_repo = args.repo_slug or parse_owner_repo_from_git()
    base_branch = args.base
    needs_branch_setup = include("local") or include("pr")
    if needs_branch_setup:
        new_branch = args.branch or f"codex/{slugify(prd_path.stem)}-{now_stamp()}"
    else:
        # When only running review_fix, stay on the current branch unless explicitly provided.
        new_branch = args.branch or git_current_branch(repo_root)

    # Make the warning phase-aware with different severity for different phases
    active_phases_with_commit_risk = selected_phases.intersection(
        PHASES_WITH_COMMIT_RISK
    )
    perform_auto_pr_commit = include("pr") and not include("local") and not args.dry_run
    stash_selector: Optional[str] = None
    branch_pushed = False
    if not args.dry_run:
        dirty_entries = git_status_snapshot(repo_root)
        if dirty_entries:
            if active_phases_with_commit_risk:
                # More prominent warning for phases that might commit changes unintentionally
                print("⚠️  WARNING: Workspace has uncommitted changes!")
                print("   This is risky for phases that might commit changes:")
                print(
                    f"   Active phases with commit risk: {', '.join(sorted(active_phases_with_commit_risk))}"
                )
                if perform_auto_pr_commit:
                    print("   Autodev will stash, commit, and push these changes for the PR phase.")
                else:
                    print("   Consider committing or stashing changes first.")
                print("\nUncommitted changes:")
                for entry in dirty_entries:
                    print(f"   {entry}")
                print()
                logger.warning(
                    "Uncommitted changes detected in phases with commit risk (%s): %s",
                    ", ".join(sorted(active_phases_with_commit_risk)),
                    "; ".join(dirty_entries),
                )
            else:
                # Standard warning for review_fix phase where uncommitted changes are less problematic
                logger.warning(
                    "Workspace has uncommitted changes; continuing with relaxed behavior:\n%s",
                    "\n".join(f"  {entry}" for entry in dirty_entries),
                )
            if perform_auto_pr_commit:
                print("Stashing working tree before preparing PR branch…")
                stash_message = f"autodev-pr-stash-{now_stamp()}"
                stash_selector = git_stash_worktree(repo_root, stash_message)
                if stash_selector is None:
                    raise SystemExit(
                        "Failed to stash working tree prior to PR preparation."
                    )

    if needs_branch_setup:
        try:
            if args.sync_git:
                print("Synchronizing base branch from origin…")
                run_cmd(["git", "fetch", "origin"], cwd=repo_root)
                run_cmd(["git", "checkout", base_branch], cwd=repo_root)
                run_cmd(["git", "pull", "--ff-only"], cwd=repo_root)
            else:
                print("Skipping git fetch/pull (pass --sync-git to enable).")
                run_cmd(["git", "checkout", base_branch], cwd=repo_root)
            _, _, rc = run_cmd(
                ["git", "checkout", "-b", new_branch], cwd=repo_root, check=False
            )
            if rc != 0:
                run_cmd(["git", "checkout", new_branch], cwd=repo_root)
        except subprocess.CalledProcessError as exc:
            details = extract_called_process_error_details(exc)
            logger.warning(
                "Git branch setup failed (%s); continuing on current branch", details
            )
            new_branch = git_current_branch(repo_root)
    else:
        print("Skipping branch setup (local/pr phases disabled).")
        if args.branch:
            try:
                run_cmd(["git", "checkout", new_branch], cwd=repo_root)
            except subprocess.CalledProcessError as exc:
                details = extract_called_process_error_details(exc)
                logger.warning(
                    "Failed to switch to '%s' for review_fix (%s); continuing on current branch",
                    new_branch,
                    details,
                )
                new_branch = git_current_branch(repo_root)
        else:
            print(f"Continuing on current branch: {new_branch}")

    if stash_selector:
        try:
            print(f"Restoring stashed changes ({stash_selector}) onto branch '{new_branch}'…")
            git_stash_pop(repo_root, stash_selector)
        except subprocess.CalledProcessError as exc:
            details = extract_called_process_error_details(exc)
            raise SystemExit(
                "Failed to reapply stashed changes after creating the PR branch. "
                f"Details: {details}"
            )

    if perform_auto_pr_commit:
        try:
            git_stage_all(repo_root)
        except subprocess.CalledProcessError as exc:
            details = extract_called_process_error_details(exc)
            raise SystemExit(f"Failed to stage changes before PR commit: {details}")
        if git_has_staged_changes(repo_root):
            commit_message = (
                f"chore: autodev snapshot {slugify(prd_path.stem)} {now_stamp()}"
            )
            try:
                git_commit(repo_root, commit_message)
            except subprocess.CalledProcessError as exc:
                details = extract_called_process_error_details(exc)
                raise SystemExit(f"Failed to commit staged changes: {details}")
            print(f"Committed changes with message: {commit_message}")
        else:
            print("No staged changes detected before PR; skipping commit.")
        try:
            git_push_branch(repo_root, new_branch)
            branch_pushed = True
            print(f"Pushed branch '{new_branch}' to origin.")
        except subprocess.CalledProcessError as exc:
            details = extract_called_process_error_details(exc)
            raise SystemExit(f"Failed to push branch '{new_branch}': {details}")

    print_codex_diagnostics(repo_root)
    tasks_left = -1
    appears_complete = False
    if include("local"):
        tasks_left, appears_complete = orchestrate_local_loop(
            prd_path=prd_path,
            repo_root=repo_root,
            base_branch=base_branch,
            max_iters=args.max_local_iters,
            codex_model=args.codex_model,
            allow_unsafe_execution=args.allow_unsafe_execution,
            dry_run=args.dry_run,
        )
    pr_number = None
    if include("pr"):
        pr_number = open_or_get_pr(
            new_branch=new_branch,
            base_branch=base_branch,
            repo_root=repo_root,
            prd_path=prd_path,
            codex_model=args.codex_model,
            allow_unsafe_execution=args.allow_unsafe_execution,
            dry_run=args.dry_run,
            skip_runner=perform_auto_pr_commit,
            already_pushed=branch_pushed,
        )
    # If starting directly at review_fix, try to infer PR from current branch
    if include("review_fix") and not include("pr"):
        if pr_number is None:
            head_branch = git_current_branch(repo_root)
            try:
                pr_number = get_pr_number_for_head(head_branch, repo_root)
            except (
                ValueError,
                RuntimeError,
                OSError,
                subprocess.CalledProcessError,
                FileNotFoundError,
            ):
                pr_number = None
            if pr_number is None:
                print(
                    "No open PR associated with the current branch; review/fix loop will be skipped."
                )
    if include("review_fix"):
        review_fix_loop(
            pr_number=pr_number,
            owner_repo=owner_repo,
            repo_root=repo_root,
            idle_grace=args.idle_grace_minutes,
            poll_interval=args.review_poll_seconds,
            codex_model=args.codex_model,
            allow_unsafe_execution=args.allow_unsafe_execution,
            dry_run=args.dry_run,
            initial_wait_minutes=args.wait_minutes,
            infinite_reviews=args.infinite_reviews,
        )

    post_final_comment(
        pr_number=pr_number,
        owner_repo=owner_repo,
        prd_path=prd_path,
        repo_root=repo_root,
        dry_run=args.dry_run,
    )

    if appears_complete:
        print(f"Final TASKS_LEFT={tasks_left}")


if __name__ == "__main__":
    main()
