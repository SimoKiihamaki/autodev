"""Test package for tools.auto_prd."""

import os
import sys
from pathlib import Path


def safe_cleanup(path: Path | str, description: str = "file") -> None:
    """Safely clean up a file or directory with proper error handling.

    Args:
        path: Path to the file or directory to clean up
        description: Human-readable description for error messages
    """
    try:
        if isinstance(path, str):
            path = Path(path)

        if path.exists():
            if path.is_dir():
                import shutil

                shutil.rmtree(path)
            else:
                path.unlink()
    except FileNotFoundError:
        # Already gone - no warning needed
        pass
    except OSError as e:
        print(
            f"Warning: Failed to clean up {description} {path}: {e}",
            file=sys.stderr,
        )
