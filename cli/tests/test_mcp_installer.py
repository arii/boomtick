import json
import pytest
from pathlib import Path
from dev_tools.handlers.mcp_installer import detect_and_install_mcp, update_host_config


def test_update_host_config_dry_run(tmp_path):
    config_file = tmp_path / "settings.json"
    status, msg = update_host_config(config_file, {"command": "boomtick-mcp"}, dry_run=True)

    assert status == "dry_run"
    assert not config_file.exists()


def test_update_host_config_execute_new_file(tmp_path):
    config_file = tmp_path / "settings.json"
    status, msg = update_host_config(config_file, {"command": "boomtick-mcp"}, dry_run=False)

    assert status == "updated"
    assert config_file.exists()

    with open(config_file, "r") as f:
        data = json.load(f)
    assert data["mcpServers"]["boomtick"]["command"] == "boomtick-mcp"


def test_update_host_config_execute_existing_file(tmp_path):
    config_file = tmp_path / "settings.json"
    initial_data = {
        "mcpServers": {
            "other_tool": {"command": "other"}
        }
    }
    with open(config_file, "w") as f:
        json.dump(initial_data, f)

    status, msg = update_host_config(config_file, {"command": "boomtick-mcp"}, dry_run=False)

    assert status == "updated"

    with open(config_file, "r") as f:
        data = json.load(f)
    assert data["mcpServers"]["other_tool"]["command"] == "other"
    assert data["mcpServers"]["boomtick"]["command"] == "boomtick-mcp"


def test_detect_and_install_mcp_custom_path(tmp_path):
    config_file = tmp_path / "custom_settings.json"
    res = detect_and_install_mcp(custom_path=str(config_file), dry_run=False)

    assert res["status"] == "success"
    assert len(res["results"]) == 1
    assert res["results"][0]["status"] == "updated"
    assert config_file.exists()
