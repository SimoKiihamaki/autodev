"""Ralph mode configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass

# Use float('inf') to represent a disabled threshold (effectively infinite)
THRESHOLD_DISABLED = float("inf")

# Environment variable names for Ralph configuration (must match Go runner)
ENV_RALPH_ENABLED = "AUTO_PRD_RALPH_ENABLED"
ENV_RALPH_ENABLE_REVIEW_ROUND = "AUTO_PRD_RALPH_ENABLE_REVIEW_ROUND"
ENV_RALPH_REVIEW_MODEL = "AUTO_PRD_RALPH_REVIEW_MODEL"
ENV_RALPH_REVIEW_TIMEOUT = "AUTO_PRD_RALPH_REVIEW_TIMEOUT"

# Canonical default model for review rounds - must match ReviewConfig, Go config, CLI
DEFAULT_REVIEW_MODEL = "claude-sonnet-4-5-20250514"


@dataclass
class RalphSettings:
    """Runtime configuration for Ralph mode features."""

    enabled: bool = False
    context_rotate_every: int = 0
    max_consecutive_failures: int = 3
    auto_add_signs: bool = True
    show_progress_log: bool = False
    show_guardrails: bool = False
    gutter_output_timeout_sec: int = 180
    gutter_no_progress_iters: int = 3

    # Review round settings
    enable_review_round: bool = True
    review_round_model: str = DEFAULT_REVIEW_MODEL
    review_round_timeout: int = 300

    @classmethod
    def from_env(cls) -> RalphSettings:
        """Create RalphSettings from environment variables (for Go TUI integration).

        This reads settings from AUTO_PRD_RALPH_* environment variables which are
        set by the Go runner. It provides a fallback path for configuration when
        the Python CLI is not used directly.
        """

        def _bool_env(key: str, default: bool = False) -> bool:
            val = os.environ.get(key, "").lower()
            if val in ("1", "true", "yes", "on"):
                return True
            if val in ("0", "false", "no", "off"):
                return False
            return default

        return cls(
            enabled=_bool_env(ENV_RALPH_ENABLED),
            enable_review_round=_bool_env(ENV_RALPH_ENABLE_REVIEW_ROUND, default=True),
            review_round_model=os.environ.get(
                ENV_RALPH_REVIEW_MODEL, DEFAULT_REVIEW_MODEL
            ),
            review_round_timeout=int(os.environ.get(ENV_RALPH_REVIEW_TIMEOUT, "300")),
        )

    def normalized(self) -> RalphSettings:
        """Return a normalized copy with safe minimums."""
        return RalphSettings(
            enabled=bool(self.enabled),
            context_rotate_every=max(0, int(self.context_rotate_every or 0)),
            max_consecutive_failures=max(1, int(self.max_consecutive_failures or 1)),
            auto_add_signs=bool(self.auto_add_signs),
            show_progress_log=bool(self.show_progress_log),
            show_guardrails=bool(self.show_guardrails),
            gutter_output_timeout_sec=max(0, int(self.gutter_output_timeout_sec or 0)),
            gutter_no_progress_iters=max(0, int(self.gutter_no_progress_iters or 0)),
            enable_review_round=bool(self.enable_review_round),
            review_round_model=str(self.review_round_model or DEFAULT_REVIEW_MODEL),
            review_round_timeout=max(30, int(self.review_round_timeout or 300)),
        )

    def stall_thresholds(self) -> tuple[float, int] | None:
        """Return StallDetector thresholds, or None if detection disabled."""
        if not self.enabled:
            return None
        no_output = self.gutter_output_timeout_sec
        no_progress = self.gutter_no_progress_iters
        if no_output <= 0 and no_progress <= 0:
            return None
        if no_output <= 0:
            no_output = THRESHOLD_DISABLED
        if no_progress <= 0:
            # Use a very large int for no_progress (can't use float('inf') for int)
            no_progress = 1_000_000_000
        return float(no_output), int(no_progress)
