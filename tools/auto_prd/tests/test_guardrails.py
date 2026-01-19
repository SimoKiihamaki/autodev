"""Tests for the guardrails module."""

import os
import tempfile
from pathlib import Path
from unittest import mock

from auto_prd.guardrails import (
    Sign,
    _get_repo_slug,
    add_sign,
    clear_guardrails,
    format_signs_for_prompt,
    get_guardrails_path,
    get_sign_count,
    load_guardrails,
    suggest_sign_from_error,
)


class TestSign:
    """Tests for the Sign dataclass."""

    def test_sign_to_markdown(self) -> None:
        """Test Sign conversion to markdown format."""
        sign = Sign(
            name="test_sign",
            trigger="Test trigger",
            instruction="Test instruction",
            added_iteration=1,
            file_context="src/test.py",
            category="test",
            phase="local",
        )
        markdown = sign.to_markdown()

        assert "## sign: test_sign" in markdown
        assert "**Trigger**: Test trigger" in markdown
        assert "**Instruction**: Test instruction" in markdown
        assert "**Added**: Iteration 1" in markdown
        assert "**File**: src/test.py" in markdown
        assert "**Category**: test" in markdown
        assert "**Phase**: local" in markdown

    def test_sign_to_dict(self) -> None:
        """Test Sign conversion to dictionary."""
        sign = Sign(
            name="test_sign",
            trigger="Test trigger",
            instruction="Test instruction",
            added_iteration=1,
            file_context="src/test.py",
            category="test",
            phase="local",
        )
        data = sign.to_dict()

        assert data["name"] == "test_sign"
        assert data["trigger"] == "Test trigger"
        assert data["instruction"] == "Test instruction"
        assert data["added_iteration"] == 1
        assert data["file_context"] == "src/test.py"
        assert data["category"] == "test"
        assert data["phase"] == "local"

    def test_sign_from_dict(self) -> None:
        """Test Sign creation from dictionary."""
        data = {
            "name": "test_sign",
            "trigger": "Test trigger",
            "instruction": "Test instruction",
            "added_iteration": 1,
            "file_context": "src/test.py",
            "category": "test",
            "phase": "local",
        }
        sign = Sign.from_dict(data)

        assert sign.name == "test_sign"
        assert sign.trigger == "Test trigger"
        assert sign.instruction == "Test instruction"
        assert sign.added_iteration == 1
        assert sign.file_context == "src/test.py"
        assert sign.category == "test"
        assert sign.phase == "local"


class TestGetGuardrailsPath:
    """Tests for get_guardrails_path."""

    def test_uses_xdg_config_home(self) -> None:
        """Test that XDG_CONFIG_HOME is used when set."""
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/custom/config"}):
            with tempfile.TemporaryDirectory() as tmpdir:
                repo_root = Path(tmpdir) / "test-repo"
                repo_root.mkdir()

                path = get_guardrails_path(repo_root)

                assert str(path).startswith("/custom/config/aprd/guardrails")

    def test_fallback_to_home(self) -> None:
        """Test fallback to ~/.config when XDG_CONFIG_HOME is not set."""
        env = os.environ.copy()
        env.pop("XDG_CONFIG_HOME", None)

        with mock.patch.dict(os.environ, env, clear=False):
            with tempfile.TemporaryDirectory() as tmpdir:
                repo_root = Path(tmpdir) / "test-repo"
                repo_root.mkdir()

                path = get_guardrails_path(repo_root)

                # Should use ~/.config/aprd/guardrails
                assert "aprd/guardrails" in str(path)


class TestGetRepoSlug:
    """Tests for _get_repo_slug."""

    def test_slug_from_directory_name(self) -> None:
        """Test generating slug from directory name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "my-test-repo"
            repo_root.mkdir()

            # Mock parse_owner_repo_from_git to return None (fallback to directory name)
            # Must mock where it's imported, not where it's defined
            with mock.patch(
                "auto_prd.guardrails.parse_owner_repo_from_git", return_value=None
            ):
                slug = _get_repo_slug(repo_root)

                assert slug == "my_test_repo"

    def test_slug_from_git_remote(self) -> None:
        """Test generating slug from git config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "test-repo"
            repo_root.mkdir()

            # Mock parse_owner_repo_from_git to return owner/repo
            # Must mock where it's imported, not where it's defined
            with mock.patch(
                "auto_prd.guardrails.parse_owner_repo_from_git",
                return_value="owner/repo-name",
            ):
                slug = _get_repo_slug(repo_root)

                assert slug == "owner_repo_name"


class TestLoadGuardrails:
    """Tests for load_guardrails."""

    def test_load_nonexistent_file(self) -> None:
        """Test loading from nonexistent file returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "load-test-repo"
            repo_root.mkdir()

            # Mock git config to avoid reading real repo
            with mock.patch(
                "auto_prd.guardrails.parse_owner_repo_from_git", return_value=None
            ):
                signs = load_guardrails(repo_root)

                assert signs == []

    def test_load_existing_file(self) -> None:
        """Test loading signs from existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "load-existing-test"
            repo_root.mkdir()

            # Mock git config to avoid reading real repo
            with mock.patch(
                "auto_prd.guardrails.parse_owner_repo_from_git", return_value=None
            ):
                guardrails_path = get_guardrails_path(repo_root)
                guardrails_path.parent.mkdir(parents=True, exist_ok=True)

                content = """## sign: test_sign
- **Trigger**: Test trigger
- **Instruction**: Test instruction
- **Added**: Iteration 1
- **File**: src/test.py
- **Category**: test
- **Phase**: local
- **Timestamp**: 2025-01-12T10:00:00Z
"""
                guardrails_path.write_text(content)

                signs = load_guardrails(repo_root)

                assert len(signs) == 1
                assert signs[0].name == "test_sign"
                assert signs[0].trigger == "Test trigger"
                assert signs[0].instruction == "Test instruction"


class TestAddSign:
    """Tests for add_sign."""

    def test_add_first_sign(self) -> None:
        """Test adding the first sign."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "add-first-test"
            repo_root.mkdir()

            # Mock git config to avoid reading real repo
            with mock.patch(
                "auto_prd.guardrails.parse_owner_repo_from_git", return_value=None
            ):
                sign = add_sign(
                    name="test_sign",
                    trigger="Test trigger",
                    instruction="Test instruction",
                    iteration=1,
                    repo_root=repo_root,
                    file_context="src/test.py",
                    category="test",
                    phase="local",
                )

                assert sign.name == "test_sign"
                assert sign.trigger == "Test trigger"

                # Verify file was created
                guardrails_path = get_guardrails_path(repo_root)
                assert guardrails_path.exists()

                content = guardrails_path.read_text()
                assert "## sign: test_sign" in content
                assert "Test trigger" in content
                assert "Test instruction" in content

    def test_add_multiple_signs(self) -> None:
        """Test adding multiple signs accumulates them."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "add-multiple-test"
            repo_root.mkdir()

            # Mock git config to avoid reading real repo
            with mock.patch(
                "auto_prd.guardrails.parse_owner_repo_from_git", return_value=None
            ):
                add_sign(
                    name="first_sign",
                    trigger="First trigger",
                    instruction="First instruction",
                    iteration=1,
                    repo_root=repo_root,
                )

                add_sign(
                    name="second_sign",
                    trigger="Second trigger",
                    instruction="Second instruction",
                    iteration=2,
                    repo_root=repo_root,
                )

                signs = load_guardrails(repo_root)
                assert len(signs) == 2
                assert signs[0].name == "first_sign"
                assert signs[1].name == "second_sign"


class TestFormatSignsForPrompt:
    """Tests for format_signs_for_prompt."""

    def test_empty_signs(self) -> None:
        """Test formatting empty signs list."""
        result = format_signs_for_prompt([])
        assert result == ""

    def test_format_single_sign(self) -> None:
        """Test formatting single sign."""
        signs = [
            Sign(
                name="test_sign",
                trigger="Test trigger",
                instruction="Test instruction",
                added_iteration=1,
                file_context="src/test.py",
            )
        ]
        result = format_signs_for_prompt(signs)

        assert "[guardrails]" in result
        assert "[test_sign]" in result
        assert "Test trigger" in result
        assert "Test instruction" in result
        assert "[/guardrails]" in result

    def test_format_multiple_signs(self) -> None:
        """Test formatting multiple signs."""
        signs = [
            Sign(
                name="first_sign",
                trigger="First trigger",
                instruction="First instruction",
                added_iteration=1,
            ),
            Sign(
                name="second_sign",
                trigger="Second trigger",
                instruction="Second instruction",
                added_iteration=2,
            ),
        ]
        result = format_signs_for_prompt(signs)

        assert "[first_sign]" in result
        assert "[second_sign]" in result
        assert "First trigger" in result
        assert "Second trigger" in result


class TestSuggestSignFromError:
    """Tests for suggest_sign_from_error."""

    def test_suggest_from_import_error(self) -> None:
        """Test suggesting sign from import error."""
        sign = suggest_sign_from_error(
            "ModuleNotFoundError: No module named 'requests'",
            iteration=1,
            _repo_root=Path("/tmp/test"),
        )

        assert sign is not None
        assert sign.name == "check_imports_before_using"
        assert sign.category == "import"

    def test_suggest_from_migration_error(self) -> None:
        """Test suggesting sign from migration error."""
        sign = suggest_sign_from_error(
            "Column already exists: users.email",
            iteration=1,
            _repo_root=Path("/tmp/test"),
        )

        assert sign is not None
        assert sign.name == "use_if_not_exists_migrations"
        assert sign.category == "migration"

    def test_suggest_from_type_error(self) -> None:
        """Test suggesting sign from type error."""
        sign = suggest_sign_from_error(
            "TypeError: Cannot convert string to int",
            iteration=1,
            _repo_root=Path("/tmp/test"),
        )

        assert sign is not None
        assert sign.name == "check_types_before_operation"
        assert sign.category == "types"

    def test_suggest_no_match(self) -> None:
        """Test that unrecognized errors return None."""
        sign = suggest_sign_from_error(
            "Some unrecognized error message",
            iteration=1,
            _repo_root=Path("/tmp/test"),
        )

        assert sign is None


class TestClearGuardrails:
    """Tests for clear_guardrails."""

    def test_clear_existing_guardrails(self) -> None:
        """Test clearing existing guardrails file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "clear-existing-test"
            repo_root.mkdir()

            # Mock git config to avoid reading real repo
            with mock.patch(
                "auto_prd.guardrails.parse_owner_repo_from_git", return_value=None
            ):
                # Add a sign first
                add_sign(
                    name="test_sign",
                    trigger="Test trigger",
                    instruction="Test instruction",
                    iteration=1,
                    repo_root=repo_root,
                )

                assert get_sign_count(repo_root) == 1

                # Clear guardrails
                clear_guardrails(repo_root)

                assert get_sign_count(repo_root) == 0

    def test_clear_nonexistent_guardrails(self) -> None:
        """Test clearing nonexistent guardrails is safe."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "clear-nonexistent-test"
            repo_root.mkdir()

            # Mock git config to avoid reading real repo
            with mock.patch(
                "auto_prd.guardrails.parse_owner_repo_from_git", return_value=None
            ):
                # Should not raise
                clear_guardrails(repo_root)
                assert get_sign_count(repo_root) == 0


class TestGetSignCount:
    """Tests for get_sign_count."""

    def test_count_empty_guardrails(self) -> None:
        """Test counting when no guardrails exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "count-empty-test"
            repo_root.mkdir()

            # Mock git config to avoid reading real repo
            with mock.patch(
                "auto_prd.guardrails.parse_owner_repo_from_git", return_value=None
            ):
                count = get_sign_count(repo_root)
                assert count == 0

    def test_count_multiple_signs(self) -> None:
        """Test counting multiple signs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "count-multiple-test"
            repo_root.mkdir()

            # Mock git config to avoid reading real repo
            with mock.patch(
                "auto_prd.guardrails.parse_owner_repo_from_git", return_value=None
            ):
                add_sign(
                    name="first_sign",
                    trigger="First",
                    instruction="Do this",
                    iteration=1,
                    repo_root=repo_root,
                )
                add_sign(
                    name="second_sign",
                    trigger="Second",
                    instruction="Do that",
                    iteration=2,
                    repo_root=repo_root,
                )
                add_sign(
                    name="third_sign",
                    trigger="Third",
                    instruction="Do other",
                    iteration=3,
                    repo_root=repo_root,
                )

                count = get_sign_count(repo_root)
                assert count == 3
