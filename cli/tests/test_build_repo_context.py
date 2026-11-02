"""
Unit tests for build-repo-context functionality, specifically minification and path safety.
"""

import importlib
import json
import pathlib
import pytest

# Load the build-repo-context module dynamically due to dashes in filename
build_repo_context_module = importlib.import_module("dev_tools.resources.build-repo-context")
safe_read_and_minify = build_repo_context_module.safe_read_and_minify
build_repo_context = build_repo_context_module.build_repo_context


def test_safe_read_and_minify_success(tmp_path):
    """Test valid code with comments and whitespace to ensure it is minified correctly."""
    test_file = tmp_path / "test.ts"
    test_file.write_text("""
    // This is a single-line comment
    export const x = {
        key: 'value', /* This is a block comment */
        nested: 'http://example.com' // Ensure URLs with // are not stripped
    };
    """, encoding="utf-8")

    minified = safe_read_and_minify(test_file, tmp_path)
    assert minified == "export const x = { key: 'value', nested: 'http://example.com' };"


def test_safe_read_and_minify_path_traversal(tmp_path):
    """Test that path traversal (accessing files outside base directory) returns empty string."""
    unauthorized_dir = tmp_path / "secret_zone"
    unauthorized_dir.mkdir()
    secret_file = unauthorized_dir / "passwords.txt"
    secret_file.write_text("my-secret-data")

    base_dir = tmp_path / "safe_zone"
    base_dir.mkdir()

    # Try to access a file outside safe_zone (path traversal)
    res = safe_read_and_minify(secret_file, base_dir)
    assert res == ""


def test_safe_read_and_minify_non_existent_file(tmp_path):
    """Test that safe_read_and_minify handles non-existent files gracefully by returning empty string."""
    non_existent = tmp_path / "does_not_exist.ts"
    res = safe_read_and_minify(non_existent, tmp_path)
    assert res == ""


def test_build_repo_context_schema_separation():
    """Test that build_repo_context writes command schema to cli-commands-schema.json

    and never clobbers cli-schema.json, leaving cli-schema.json containing only models.
    """
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    cli_schema_path = repo_root / "cli" / "dev_tools" / "cli-schema.json"
    cli_commands_schema_path = repo_root / "cli" / "dev_tools" / "cli-commands-schema.json"

    initial_cli_schema = cli_schema_path.read_text(encoding="utf-8")

    ctx = build_repo_context()

    assert "cli_schema" in ctx
    assert "subcommands" in ctx["cli_schema"]

    # cli-commands-schema.json should exist and have command keys
    assert cli_commands_schema_path.exists()
    commands_data = json.loads(cli_commands_schema_path.read_text(encoding="utf-8"))
    assert "subcommands" in commands_data
    assert "tool_name" in commands_data

    # cli-schema.json should contain models and not command keys
    models_data = json.loads(cli_schema_path.read_text(encoding="utf-8"))
    assert "models" in models_data
    assert len(models_data["models"]) > 0
    assert "subcommands" not in models_data
    assert "tool_name" not in models_data
    assert "base_command" not in models_data

    # Ensure cli-schema.json content is unchanged
    assert cli_schema_path.read_text(encoding="utf-8") == initial_cli_schema


def test_build_repo_context_schema_gen_failure_propagates(monkeypatch):
    """Test that if generate_schema throws, build_repo_context fails loudly

    and cli-schema.json is not clobbered with half-written command schema.
    """
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    cli_schema_path = repo_root / "cli" / "dev_tools" / "cli-schema.json"

    initial_cli_schema = cli_schema_path.read_text(encoding="utf-8")

    def mock_generate_schema():
        raise RuntimeError("Simulated model schema generation failure")

    monkeypatch.setattr("dev_tools.schema_gen.generate_schema", mock_generate_schema)

    with pytest.raises(RuntimeError, match="Simulated model schema generation failure"):
        build_repo_context()

    # Verify cli-schema.json was not overwritten or corrupted
    assert cli_schema_path.read_text(encoding="utf-8") == initial_cli_schema
    models_data = json.loads(cli_schema_path.read_text(encoding="utf-8"))
    assert "models" in models_data
    assert "subcommands" not in models_data
