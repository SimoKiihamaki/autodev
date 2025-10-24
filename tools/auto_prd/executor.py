"""Executor policy resolution and verification."""

from __future__ import annotations

import os
import subprocess
from typing import Set, Tuple

from .command_checks import require_cmd
from .logging_utils import logger
from .policy import (
    EXECUTOR_CHOICES,
    EXECUTOR_POLICY_DEFAULT,
    MAX_FALLBACK_ATTEMPTS,
    build_required_list,
    get_fallback_policy,
    set_executor_policy,
)


class AutoPrdError(RuntimeError):
    """Raised when executor policy resolution fails."""


def _verify_required_commands(
    required: list[str],
    executor_policy: str,
    verified_commands: Set[str],
) -> Tuple[bool, str, Set[str]]:
    policy_changed = False
    for cmd_name in required:
        try:
            require_cmd(cmd_name)
            verified_commands.add(cmd_name)
        except RuntimeError as err:
            fallback_policy = get_fallback_policy(executor_policy)
            if fallback_policy:
                fallback_requires = set(build_required_list(fallback_policy))
                if cmd_name not in fallback_requires:
                    policy_changed = True
                    logger.warning(
                        "%s CLI check failed under policy %s; attempting fallback to %s. Details: %s",
                        cmd_name,
                        executor_policy,
                        fallback_policy,
                        err,
                    )
                    executor_policy = fallback_policy
                    break
            raise AutoPrdError(f"{executor_policy}: command verification failed for '{cmd_name}': {err}") from err
    return policy_changed, executor_policy, verified_commands


def resolve_executor_policy(policy_arg: str | None) -> Tuple[str, str, Set[str]]:
    policy_from_env = os.getenv("AUTO_PRD_EXECUTOR_POLICY")
    executor_policy = policy_arg or policy_from_env or EXECUTOR_POLICY_DEFAULT
    if executor_policy not in EXECUTOR_CHOICES:
        raise AutoPrdError(f"Invalid executor policy: {executor_policy}")
    set_executor_policy(executor_policy)

    verified_commands: Set[str] = set()
    fallback_attempts = 0
    executor_policy_chain = []
    initial_executor_policy = executor_policy
    while True:
        executor_policy_chain.append(executor_policy)
        policy_changed, executor_policy, verified_commands = _verify_required_commands(
            build_required_list(executor_policy), executor_policy, verified_commands
        )
        set_executor_policy(executor_policy)
        if not policy_changed:
            break
        fallback_attempts += 1
        if fallback_attempts >= MAX_FALLBACK_ATTEMPTS:
            last_required = build_required_list(executor_policy)
            failed_commands = [cmd for cmd in last_required if cmd not in verified_commands]

            cycle_detected = False
            cycle_info = ""
            if len(executor_policy_chain) != len(set(executor_policy_chain)):
                seen_indices = {}
                for i, policy in enumerate(executor_policy_chain):
                    if policy in seen_indices:
                        cycle_start = seen_indices[policy]
                        cycle_policies = executor_policy_chain[cycle_start:i]
                        cycle_detected = True
                        cycle_info = f"Detected cycle: {' -> '.join(cycle_policies)} -> {policy}"
                        break
                    seen_indices[policy] = i

            error_type = "Cycle detected" if cycle_detected else "Persistent failure"
            cycle_message = f"\n{cycle_info}" if cycle_detected else ""

            raise AutoPrdError(
                "Exceeded maximum fallback attempts while verifying required commands.\n"
                f"{error_type} in executor policy fallback logic.{cycle_message}\n"
                f"Executor policy chain tried: {executor_policy_chain}\n"
                f"Commands that failed to verify: {failed_commands}"
            )

    logger.info(
        "Using executor policy: %s%s",
        executor_policy,
        f" (fallback from {initial_executor_policy})" if executor_policy != initial_executor_policy else "",
    )
    return executor_policy, initial_executor_policy, verified_commands
