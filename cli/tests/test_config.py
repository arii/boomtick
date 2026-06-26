import json
import os
import pytest
from pathlib import Path
from dev_tools_sdk.config import load_project_config, ProjectConfig

def test_load_default_config(tmp_path):
    # Test loading when file doesn't exist
    config = load_project_config(tmp_path / "non_existent.json")
    assert isinstance(config, ProjectConfig)
    assert config.base_branch == "origin/main"
    assert config.monolithic_pr_threshold == 3
    assert "src/layouts/" in config.core_dirs

def test_load_custom_config(tmp_path):
    config_file = tmp_path / "project_config.json"
    data = {
        "base_branch": "develop",
        "monolithic_pr_threshold": 5,
        "core_dirs": ["custom/"],
        "max_diff_chars": 50000,
        "ai_synthesis_model": "gpt-4o"
    }
    config_file.write_text(json.dumps(data))

    config = load_project_config(config_file)
    assert config.base_branch == "develop"
    assert config.monolithic_pr_threshold == 5
    assert config.core_dirs == ["custom/"]
    assert config.max_diff_chars == 50000
    assert config.ai_synthesis_model == "gpt-4o"

def test_type_coercion(tmp_path):
    config_file = tmp_path / "project_config.json"
    data = {
        "monolithic_pr_threshold": "10",
        "max_diff_chars": "60000"
    }
    config_file.write_text(json.dumps(data))

    config = load_project_config(config_file)
    assert config.monolithic_pr_threshold == 10
    assert config.max_diff_chars == 60000

def test_invalid_json(tmp_path):
    config_file = tmp_path / "invalid.json"
    config_file.write_text("{ invalid json }")

    config = load_project_config(config_file)
    # Should fallback to defaults
    assert config.base_branch == "origin/main"

def test_legacy_repo_name(tmp_path):
    config_file = tmp_path / "project_config.json"
    data = {
        "repo_name": "owner/repo"
    }
    config_file.write_text(json.dumps(data))

    config = load_project_config(config_file)
    assert config.github_repo == "owner/repo"
