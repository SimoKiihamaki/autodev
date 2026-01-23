"""Configuration file support for support-mode.

Supports YAML and TOML configuration files (.support.yaml, .support.toml).
Configuration can be placed in:
1. Current working directory
2. Repository root (.support.yaml/toml)
3. XDG config home (~/.config/support-mode/config.yaml/toml)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class NotificationConfig:
    """Configuration for desktop notifications."""

    enabled: bool = True
    use_webhook: bool = False
    webhook_url: str = ""
    webhook_format: str = "json"  # json or text


@dataclass
class MonitoringConfig:
    """Configuration for monitoring behavior."""

    poll_seconds: int = 120
    recent_commits_limit: int = 8
    max_items_display: int = 8
    verbose: bool = False
    log_level: str = "INFO"


@dataclass
class ValidationConfig:
    """Configuration for validation checks."""

    check_whitespace: bool = True
    check_conflicts: bool = True
    validate_tracker: bool = True
    compare_prd: bool = True


@dataclass
class OutputConfig:
    """Configuration for output format."""

    format: str = "console"  # console, json, jsonl
    show_timestamps: bool = True
    colors: bool = True


@dataclass
class MultiRepoConfig:
    """Configuration for multi-repository monitoring."""

    enabled: bool = False
    repos: list[dict[str, str]] = field(default_factory=list)


@dataclass
class Config:
    """Complete configuration for support-mode.

    Attributes:
        monitoring: Monitoring behavior settings.
        validation: Validation check settings.
        notifications: Notification settings.
        output: Output format settings.
        multi_repo: Multi-repository settings.
    """

    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    multi_repo: MultiRepoConfig = field(default_factory=MultiRepoConfig)

    @classmethod
    def load(
        cls, config_path: Path | None = None, repo_root: Path | None = None
    ) -> "Config":
        """Load configuration from file.

        Searches in order:
        1. Explicit config_path
        2. .support.yaml or .support.toml in repo_root
        3. .support.yaml or .support.toml in current directory
        4. ~/.config/support-mode/config.yaml or config.toml

        Args:
            config_path: Explicit path to config file.
            repo_root: Repository root directory.

        Returns:
            Config instance with defaults or loaded values.
        """
        config_file = cls._find_config(config_path, repo_root)
        if config_file is None:
            logger.debug("No config file found, using defaults")
            return cls()

        return cls._load_from_file(config_file)

    @classmethod
    def _find_config(
        cls, config_path: Path | None, repo_root: Path | None
    ) -> Path | None:
        """Find configuration file.

        Args:
            config_path: Explicit path to check.
            repo_root: Repository root to check.

        Returns:
            Path to config file or None.
        """
        # Explicit path
        if config_path and config_path.exists():
            return config_path

        # Repo root
        if repo_root:
            for name in [".support.yaml", ".support.yml", ".support.toml"]:
                path = repo_root / name
                if path.exists():
                    return path

        # Current directory
        cwd = Path.cwd()
        for name in [".support.yaml", ".support.yml", ".support.toml"]:
            path = cwd / name
            if path.exists():
                return path

        # XDG config home
        xdg_config = os.getenv("XDG_CONFIG_HOME")
        if xdg_config:
            config_dir = Path(xdg_config) / "support-mode"
        else:
            config_dir = Path.home() / ".config" / "support-mode"

        for name in ["config.yaml", "config.yml", "config.toml"]:
            path = config_dir / name
            if path.exists():
                return path

        return None

    @classmethod
    def _load_from_file(cls, config_path: Path) -> "Config":
        """Load config from specific file.

        Args:
            config_path: Path to config file.

        Returns:
            Config instance.
        """
        suffix = config_path.suffix.lower()

        if suffix in [".yaml", ".yml"]:
            return cls._load_yaml(config_path)
        elif suffix == ".toml":
            return cls._load_toml(config_path)
        else:
            logger.warning(f"Unknown config format: {suffix}, using defaults")
            return cls()

    @classmethod
    def _load_yaml(cls, config_path: Path) -> "Config":
        """Load YAML config file.

        Args:
            config_path: Path to YAML file.

        Returns:
            Config instance.
        """
        try:
            import yaml

            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
            return cls._from_dict(data)
        except ImportError:
            logger.warning("PyYAML not installed, cannot load YAML config")
            return cls()
        except (OSError, yaml.YAMLError) as e:
            logger.warning(f"Failed to load YAML config: {e}")
            return cls()

    @classmethod
    def _load_toml(cls, config_path: Path) -> "Config":
        """Load TOML config file.

        Args:
            config_path: Path to TOML file.

        Returns:
            Config instance.
        """
        try:
            import tomli

            try:
                with open(config_path, "rb") as f:
                    data = tomli.load(f)
                return cls._from_dict(data)
            except (OSError, tomli.TOMLDecodeError):
                logger.warning(f"Failed to load TOML config: {config_path}")
                return cls()
        except ImportError:
            # Fallback to tomllib (Python 3.11+)
            try:
                import tomllib

                try:
                    with open(config_path, "rb") as f:
                        data = tomllib.load(f)
                    return cls._from_dict(data)
                except (OSError, tomllib.TOMLDecodeError):
                    logger.warning(f"Failed to load TOML config: {config_path}")
                    return cls()
            except ImportError:
                logger.warning("No TOML library available")
                return cls()

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "Config":
        """Create Config from dictionary.

        Args:
            data: Configuration dictionary.

        Returns:
            Config instance.
        """
        monitoring_data = data.get("monitoring", {})
        monitoring = MonitoringConfig(
            poll_seconds=monitoring_data.get("poll_seconds", 120),
            recent_commits_limit=monitoring_data.get("recent_commits_limit", 8),
            max_items_display=monitoring_data.get("max_items_display", 8),
            verbose=monitoring_data.get("verbose", False),
            log_level=monitoring_data.get("log_level", "INFO"),
        )

        validation_data = data.get("validation", {})
        validation = ValidationConfig(
            check_whitespace=validation_data.get("check_whitespace", True),
            check_conflicts=validation_data.get("check_conflicts", True),
            validate_tracker=validation_data.get("validate_tracker", True),
            compare_prd=validation_data.get("compare_prd", True),
        )

        notifications_data = data.get("notifications", {})
        notifications = NotificationConfig(
            enabled=notifications_data.get("enabled", True),
            use_webhook=notifications_data.get("use_webhook", False),
            webhook_url=notifications_data.get("webhook_url", ""),
            webhook_format=notifications_data.get("webhook_format", "json"),
        )

        output_data = data.get("output", {})
        output = OutputConfig(
            format=output_data.get("format", "console"),
            show_timestamps=output_data.get("show_timestamps", True),
            colors=output_data.get("colors", True),
        )

        multi_repo_data = data.get("multi_repo", {})
        multi_repo = MultiRepoConfig(
            enabled=multi_repo_data.get("enabled", False),
            repos=multi_repo_data.get("repos", []),
        )

        return cls(
            monitoring=monitoring,
            validation=validation,
            notifications=notifications,
            output=output,
            multi_repo=multi_repo,
        )

    def save_example(self, path: Path) -> None:
        """Save an example config file.

        Args:
            path: Path to save example config.
        """
        suffix = path.suffix.lower()

        if suffix in [".yaml", ".yml"]:
            self._save_yaml_example(path)
        elif suffix == ".toml":
            self._save_toml_example(path)
        else:
            logger.warning(f"Unknown config format: {suffix}")

    def _save_yaml_example(self, path: Path) -> None:
        """Save YAML example config."""
        example = """# Support Mode Configuration Example

monitoring:
  poll_seconds: 120  # How often to check for updates (seconds)
  recent_commits_limit: 8  # How many commits to show
  max_items_display: 8  # Max items to show in each section
  verbose: false
  log_level: INFO

validation:
  check_whitespace: true  # Run 'git diff --check'
  check_conflicts: true  # Check for conflict markers
  validate_tracker: true  # Validate tracker.json structure
  compare_prd: true  # Compare PRD checkboxes with tracker tasks

notifications:
  enabled: true  # Enable desktop notifications
  use_webhook: false  # Send notifications to webhook
  webhook_url: ""  # Webhook URL
  webhook_format: json  # json or text

output:
  format: console  # console, json, jsonl
  show_timestamps: true
  colors: true

multi_repo:
  enabled: false  # Monitor multiple repositories
  repos: []  # List of {path: "..."} dicts
"""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(example)
        except OSError as e:
            logger.warning(f"Could not write example config: {e}")

    def _save_toml_example(self, path: Path) -> None:
        """Save TOML example config."""
        example = """# Support Mode Configuration Example

[monitoring]
poll_seconds = 120  # How often to check for updates (seconds)
recent_commits_limit = 8  # How many commits to show
max_items_display = 8  # Max items to show in each section
verbose = false
log_level = "INFO"

[validation]
check_whitespace = true  # Run 'git diff --check'
check_conflicts = true  # Check for conflict markers
validate_tracker = true  # Validate tracker.json structure
compare_prd = true  # Compare PRD checkboxes with tracker tasks

[notifications]
enabled = true  # Enable desktop notifications
use_webhook = false  # Send notifications to webhook
webhook_url = ""  # Webhook URL
webhook_format = "json"  # json or text

[output]
format = "console"  # console, json, jsonl
show_timestamps = true
colors = true

[multi_repo]
enabled = false  # Monitor multiple repositories
repos = []  # List of {path = "..."} dicts
"""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(example)
        except OSError as e:
            logger.warning(f"Could not write example config: {e}")
