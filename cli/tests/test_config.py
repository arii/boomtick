# pylint: disable=missing-docstring
import json
import pytest

from dev_tools.config import load_project_config


def test_load_default_config(tmp_path, monkeypatch):
    # Test loading when file doesn't exist (should fail due to strict checking)
    monkeypatch.chdir(tmp_path)
    # Mock _detect_repo_name to return a valid string, so we can test missing vite_base_path
    monkeypatch.setattr("dev_tools.config._detect_repo_name", lambda: "owner/repo")
    with pytest.raises(ValueError, match="Missing required configuration: vite_base_path"):
        load_project_config(tmp_path / "non_existent.json")

    # Mock _detect_repo_name to return None, so we can test missing github_repo
    monkeypatch.setattr("dev_tools.config._detect_repo_name", lambda: None)
    with pytest.raises(ValueError, match="Missing required configuration: github_repo"):
        load_project_config(tmp_path / "non_existent.json")


def test_load_custom_config(tmp_path):
    config_file = tmp_path / "project_config.json"
    data = {
        "github_repo": "owner/repo",
        "vite_base_path": "/test/",
        "base_branch": "develop",
        "monolithic_pr_threshold": 5,
        "core_dirs": ["custom/"],
        "max_diff_chars": 50000,
        "ai_synthesis_model": "gpt-4o",
    }
    config_file.write_text(json.dumps(data))

    config = load_project_config(config_file)
    assert config.github_repo == "owner/repo"
    assert config.vite_base_path == "/test/"
    assert config.base_branch == "develop"
    assert config.monolithic_pr_threshold == 5
    assert config.core_dirs == ["custom/"]
    assert config.max_diff_chars == 50000
    assert config.ai_synthesis_model == "gpt-4o"


def test_type_coercion(tmp_path):
    config_file = tmp_path / "project_config.json"
    data = {
        "github_repo": "owner/repo",
        "vite_base_path": "/",
        "monolithic_pr_threshold": "10",
        "max_diff_chars": "60000"
    }
    config_file.write_text(json.dumps(data))

    config = load_project_config(config_file)
    assert config.monolithic_pr_threshold == 10
    assert config.max_diff_chars == 60000


def test_invalid_json(tmp_path, monkeypatch):
    config_file = tmp_path / "invalid.json"
    config_file.write_text("{ invalid json }")
    monkeypatch.setattr("dev_tools.config._detect_repo_name", lambda: None)

    with pytest.raises(ValueError, match="Missing required configuration: github_repo"):
        load_project_config(config_file)


def test_legacy_repo_name(tmp_path):
    config_file = tmp_path / "project_config.json"
    data = {"repo_name": "owner/repo", "vite_base_path": "/"}
    config_file.write_text(json.dumps(data))

    config = load_project_config(config_file)
    assert config.github_repo == "owner/repo"
