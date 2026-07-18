"""
Unit tests for build-repo-context functionality, specifically minification and path safety.
"""

import importlib

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
