"""Tests for configuration file support."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from support_mode.config_file import Config, MonitoringConfig, NotificationConfig


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


class TestConfig:
    """Tests for Config class."""

    def test_default_config(self):
        """Default configuration should have sensible defaults."""
        config = Config()

        assert config.monitoring.poll_seconds == 120
        assert config.validation.check_whitespace is True
        assert config.notifications.enabled is True
        assert config.output.format == "console"

    def test_load_from_yaml(self, temp_dir):
        """Load configuration from YAML file."""
        config_content = """
monitoring:
  poll_seconds: 60
  verbose: true

notifications:
  enabled: false
"""
        config_path = temp_dir / ".support.yaml"
        config_path.write_text(config_content)

        config = Config.load(config_path)

        assert config.monitoring.poll_seconds == 60
        assert config.monitoring.verbose is True
        assert config.notifications.enabled is False

    def test_load_from_toml(self, temp_dir):
        """Load configuration from TOML file."""
        config_content = """
[monitoring]
poll_seconds = 90
verbose = true

[notifications]
enabled = false
"""
        config_path = temp_dir / ".support.toml"
        config_path.write_text(config_content)

        config = Config.load(config_path)

        assert config.monitoring.poll_seconds == 90
        assert config.monitoring.verbose is True
        assert config.notifications.enabled is False

    def test_find_config_in_repo_root(self, temp_dir):
        """Config should be found in repo root."""
        config_content = """
monitoring:
  poll_seconds: 30
"""
        config_path = temp_dir / ".support.yaml"
        config_path.write_text(config_content)

        config = Config.load(repo_root=temp_dir)

        assert config.monitoring.poll_seconds == 30

    def test_no_config_returns_defaults(self, temp_dir):
        """Missing config should return defaults."""
        config = Config.load(repo_root=temp_dir)

        assert config.monitoring.poll_seconds == 120
        assert config.notifications.enabled is True

    def test_save_yaml_example(self, temp_dir):
        """Save example YAML config."""
        config = Config()
        example_path = temp_dir / "example.yaml"

        config.save_example(example_path)

        assert example_path.exists()
        content = example_path.read_text()
        assert "monitoring:" in content
        assert "poll_seconds:" in content

    def test_save_toml_example(self, temp_dir):
        """Save example TOML config."""
        config = Config()
        example_path = temp_dir / "example.toml"

        config.save_example(example_path)

        assert example_path.exists()
        content = example_path.read_text()
        assert "[monitoring]" in content
        assert "poll_seconds" in content


@pytest.mark.skipif(not os.getenv("CI"), reason="Only run in CI")
class TestConfigFormat:
    """Test config format compatibility."""

    def test_all_required_sections_in_example(self, temp_dir):
        """Example config should have all sections."""
        config = Config()
        example_path = temp_dir / "example.yaml"

        config.save_example(example_path)
        content = example_path.read_text()

        # Check all sections are present
        assert "monitoring:" in content
        assert "validation:" in content
        assert "notifications:" in content
        assert "output:" in content
        assert "multi_repo:" in content
