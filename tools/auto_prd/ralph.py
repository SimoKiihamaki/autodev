"""Ralph mode configuration helpers."""

from __future__ import annotations

from dataclasses import dataclass

# Use float('inf') to represent a disabled threshold (effectively infinite)
THRESHOLD_DISABLED = float("inf")


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

    def normalized(self) -> "RalphSettings":
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
