"""Tests for Ralph mode configuration module."""

from tools.auto_prd.ralph import THRESHOLD_DISABLED, RalphSettings


class TestRalphSettings:
    """Tests for RalphSettings dataclass."""

    def test_default_values(self) -> None:
        """Test that RalphSettings has sensible defaults."""
        settings = RalphSettings()

        assert settings.enabled is False
        assert settings.context_rotate_every == 0
        assert settings.max_consecutive_failures == 3
        assert settings.auto_add_signs is True
        assert settings.show_progress_log is False
        assert settings.show_guardrails is False
        assert settings.gutter_output_timeout_sec == 180
        assert settings.gutter_no_progress_iters == 3
        # Review round defaults
        assert settings.enable_review_round is True
        assert settings.review_round_model == "claude-sonnet-4-5-20250514"
        assert settings.review_round_timeout == 300

    def test_normalized_enables_boolean_conversion(self) -> None:
        """Test that normalized() converts boolean values correctly."""
        settings = RalphSettings(
            enabled=1,  # Truthy int
            auto_add_signs="yes",  # Truthy string
            show_progress_log=0,  # Falsy int
        )
        normalized = settings.normalized()

        assert normalized.enabled is True
        assert normalized.auto_add_signs is True
        assert normalized.show_progress_log is False

    def test_normalized_enforces_minimums(self) -> None:
        """Test that normalized() enforces minimum values."""
        settings = RalphSettings(
            context_rotate_every=-5,
            max_consecutive_failures=0,
            gutter_output_timeout_sec=-10,
            gutter_no_progress_iters=-1,
        )
        normalized = settings.normalized()

        assert normalized.context_rotate_every == 0
        assert normalized.max_consecutive_failures == 1
        assert normalized.gutter_output_timeout_sec == 0
        assert normalized.gutter_no_progress_iters == 0

    def test_normalized_handles_none_values(self) -> None:
        """Test that normalized() handles None values correctly."""
        settings = RalphSettings(
            context_rotate_every=None,
            max_consecutive_failures=None,
            gutter_output_timeout_sec=None,
            gutter_no_progress_iters=None,
        )
        normalized = settings.normalized()

        assert normalized.context_rotate_every == 0
        assert normalized.max_consecutive_failures == 1
        assert normalized.gutter_output_timeout_sec == 0
        assert normalized.gutter_no_progress_iters == 0

    def test_normalized_handles_review_round_fields(self) -> None:
        """Test that normalized() handles review round fields correctly."""
        settings = RalphSettings(
            enable_review_round=0,  # Falsy int
            review_round_model=None,  # None should fall back to default
            review_round_timeout=10,  # Below minimum 30 seconds
        )
        normalized = settings.normalized()

        # Boolean conversion
        assert normalized.enable_review_round is False
        # Fallback to default model when None
        assert normalized.review_round_model == "claude-sonnet-4-5-20250514"
        # Minimum timeout enforcement (30 seconds)
        assert normalized.review_round_timeout == 30

    def test_normalized_applies_review_round_fallback_defaults(self) -> None:
        """Test that normalized() applies fallback defaults for review round fields."""
        settings = RalphSettings(
            enable_review_round=None,
            review_round_model="",
            review_round_timeout=None,
        )
        normalized = settings.normalized()

        assert normalized.enable_review_round is False
        assert normalized.review_round_model == "claude-sonnet-4-5-20250514"
        assert normalized.review_round_timeout == 300  # Default timeout

    def test_stall_thresholds_returns_none_when_disabled(self) -> None:
        """Test that stall_thresholds() returns None when Ralph is disabled."""
        settings = RalphSettings(enabled=False)

        assert settings.stall_thresholds() is None

    def test_stall_thresholds_returns_none_when_both_thresholds_zero(self) -> None:
        """Test that stall_thresholds() returns None when both thresholds are <= 0."""
        settings = RalphSettings(
            enabled=True,
            gutter_output_timeout_sec=0,
            gutter_no_progress_iters=0,
        )

        assert settings.stall_thresholds() is None

    def test_stall_thresholds_uses_inf_for_disabled_timeout(self) -> None:
        """Test that stall_thresholds() uses inf for disabled timeout."""
        settings = RalphSettings(
            enabled=True,
            gutter_output_timeout_sec=0,
            gutter_no_progress_iters=3,
        )

        thresholds = settings.stall_thresholds()
        assert thresholds is not None
        no_output, no_progress = thresholds

        assert no_output == THRESHOLD_DISABLED
        assert no_progress == 3

    def test_stall_thresholds_uses_large_int_for_disabled_progress(self) -> None:
        """Test that stall_thresholds() uses large int for disabled progress."""
        settings = RalphSettings(
            enabled=True,
            gutter_output_timeout_sec=180,
            gutter_no_progress_iters=0,
        )

        thresholds = settings.stall_thresholds()
        assert thresholds is not None
        no_output, no_progress = thresholds

        assert no_output == 180.0
        assert no_progress == 1_000_000_000

    def test_stall_thresholds_returns_configured_values(self) -> None:
        """Test that stall_thresholds() returns configured values."""
        settings = RalphSettings(
            enabled=True,
            gutter_output_timeout_sec=120,
            gutter_no_progress_iters=5,
        )

        thresholds = settings.stall_thresholds()
        assert thresholds is not None
        no_output, no_progress = thresholds

        assert no_output == 120.0
        assert no_progress == 5

    def test_stall_thresholds_converts_timeout_to_float(self) -> None:
        """Test that stall_thresholds() converts timeout to float."""
        settings = RalphSettings(
            enabled=True,
            gutter_output_timeout_sec=100,
            gutter_no_progress_iters=2,
        )

        thresholds = settings.stall_thresholds()
        assert thresholds is not None
        no_output, no_progress = thresholds

        assert isinstance(no_output, float)
        assert no_output == 100.0
        assert isinstance(no_progress, int)


class TestModuleConstants:
    """Tests for module-level constants."""

    def test_threshold_disabled_is_infinity(self) -> None:
        """Test that THRESHOLD_DISABLED is float('inf')."""
        assert float("inf") == THRESHOLD_DISABLED
        assert isinstance(THRESHOLD_DISABLED, float)
