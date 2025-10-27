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


def get_project_root() -> Path:
    """Get the project root directory dynamically.

    Starts from the current file location and walks up the directory tree
    looking for common project markers (.git or go.mod files).

    Returns:
        Path to the project root directory. Falls back to current working
        directory if no markers are found.
    """
    # Start from the current file location and walk up to find .git or go.mod
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".git").exists() or (current / "go.mod").exists():
            return current
        current = current.parent

    # Fallback to current working directory if no markers found
    return Path.cwd()
