"""Executor policy configuration and selection."""

from __future__ import annotations

import os
from typing import Callable, Optional, Tuple

from .agents import claude_exec, codex_exec
from .logging_utils import logger


EXECUTOR_CHOICES = {"codex-first", "codex-only", "claude-only"}
EXECUTOR_POLICY_DEFAULT = "codex-first"
EXECUTOR_POLICY = os.getenv("AUTO_PRD_EXECUTOR_POLICY") or EXECUTOR_POLICY_DEFAULT

FALLBACK_POLICIES = {"codex-first": "codex-only"}
COMMAND_FALLBACK_CONFIG = {"claude": {"codex-first"}}


def _compute_max_fallback_attempts(fallback_policies: dict) -> int:
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
    return max_chain + 1


MAX_FALLBACK_ATTEMPTS = _compute_max_fallback_attempts(FALLBACK_POLICIES)


def get_fallback_policy(policy: str) -> Optional[str]:
    return FALLBACK_POLICIES.get(policy)


def build_required_list(policy: str) -> list[str]:
    core_deps = ["coderabbit", "git", "gh"]
    if policy == "codex-first":
        return core_deps + ["codex", "claude"]
    if policy == "codex-only":
        return core_deps + ["codex"]
    if policy == "claude-only":
        return core_deps + ["claude"]
    raise ValueError(f"Unknown executor policy: {policy}")


def set_executor_policy(value: str) -> None:
    global EXECUTOR_POLICY
    selected = (value or "").strip().lower()
    if selected not in EXECUTOR_CHOICES:
        raise ValueError(f"Unknown executor policy: {value}")
    EXECUTOR_POLICY = selected


def policy_runner(policy: str | None, i: int | None = None, phase: str = "implement") -> Tuple[Callable[..., str], str]:
    env_key_map = {
        "implement": "AUTO_PRD_EXECUTOR_IMPLEMENT",
        "fix": "AUTO_PRD_EXECUTOR_FIX",
        "pr": "AUTO_PRD_EXECUTOR_PR",
        "review_fix": "AUTO_PRD_EXECUTOR_REVIEW_FIX",
    }
    override_key = env_key_map.get(phase)
    if override_key:
        override = (os.getenv(override_key) or "").strip().lower()
        if override in ("codex", "claude"):
            return (codex_exec, "Codex") if override == "codex" else (claude_exec, "Claude")

    selected = (policy or EXECUTOR_POLICY).strip().lower()
    if selected not in EXECUTOR_CHOICES:
        logger.warning("Unknown executor policy %s; defaulting to %s", selected, EXECUTOR_POLICY_DEFAULT)
        selected = EXECUTOR_POLICY_DEFAULT

    if selected == "codex-only":
        return codex_exec, "Codex"
    if selected == "claude-only":
        return claude_exec, "Claude"

    if phase in ("pr", "review_fix"):
        return claude_exec, "Claude"
    if i == 1:
        return codex_exec, "Codex"
    return claude_exec, "Claude"


def policy_fallback_runner(
    command_name: str,
    policy: str,
    executor_factory: Callable[[str], Callable[[], str]],
    *,
    verify: Callable[[str], bool] | None = None,
) -> str:
    attempts = 0
    current_policy = policy
    while attempts < MAX_FALLBACK_ATTEMPTS and current_policy:
        attempts += 1
        try:
            set_executor_policy(current_policy)
            executor = executor_factory(current_policy)
            result = executor()
            if verify is None or verify(result):
                return result
        except Exception as exc:  # pragma: no cover - fallback best effort
            logger.warning("Executor %s failed under policy %s: %s", command_name, current_policy, exc)

        fallback = get_fallback_policy(current_policy)
        if not fallback:
            break
        logger.info("Falling back from %s to %s for %s", current_policy, fallback, command_name)
        current_policy = fallback

    raise RuntimeError(f"All fallbacks exhausted for {command_name} (policy {policy})")
