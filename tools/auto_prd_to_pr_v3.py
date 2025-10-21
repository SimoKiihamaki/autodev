#!/usr/bin/env python3
"""Compatibility wrapper for the refactored auto PRD pipeline."""

try:
    from tools.auto_prd import main  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - fallback for script invocation
    from auto_prd.cli import main


if __name__ == "__main__":
    main()
