"""Support Mode - Framework-agnostic continuous monitoring and review tool.

Provides continuous monitoring and review capabilities for AI-assisted development
that work independently of any specific coding framework.
"""

__version__ = "0.2.0"

from .cli import main
from .command import CommandResult, run_cmd
from .config_file import Config
from .guardrails import Sign, load_guardrails
from .tracker import compute_prd_hash, get_tracker_path, load_tracker, validate_tracker
from .verification import VerificationPersistence, VerificationStatus, VerifierResult
from .verification_backends import (
    CustomBackend,
    ManualBackend,
    PytestBackend,
    VerificationBackend,
    VerificationMonitor,
)

__all__ = [
    # Version
    "__version__",
    # CLI
    "main",
    # Command execution
    "CommandResult",
    "run_cmd",
    # Configuration
    "Config",
    # Guardrails
    "Sign",
    "load_guardrails",
    # Tracker
    "compute_prd_hash",
    "get_tracker_path",
    "load_tracker",
    "validate_tracker",
    # Verification
    "VerificationPersistence",
    "VerificationStatus",
    "VerifierResult",
    # Verification backends
    "VerificationBackend",
    "PytestBackend",
    "CustomBackend",
    "ManualBackend",
    "VerificationMonitor",
]
