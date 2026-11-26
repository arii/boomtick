import json
from pathlib import Path
from dev_tools.handlers.mcp_installer import detect_and_install_mcp, update_host_config


def test_update_host_config_dry_run(tmp_path):
    config_file = tmp_path / "settings.json"
    status, _msg = update_host_config(
        config_file, {"command": "boomtick-mcp"}, dry_run=True
    )

    assert status == "dry_run"
    assert not config_file.exists()


def test_update_host_config_execute_new_file(tmp_path):
    config_file = tmp_path / "settings.json"
    status, _msg = update_host_config(
        config_file, {"command": "boomtick-mcp"}, dry_run=False
    )

    assert status == "updated"
    assert config_file.exists()

    with open(config_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["mcpServers"]["boomtick"]["command"] == "boomtick-mcp"


def test_update_host_config_execute_existing_file(tmp_path):
    config_file = tmp_path / "settings.json"
    initial_data = {"mcpServers": {"other_tool": {"command": "other"}}}
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(initial_data, f)

    status, _msg = update_host_config(
        config_file, {"command": "boomtick-mcp"}, dry_run=False
    )

    assert status == "updated"

    with open(config_file, "r", encoding="utf-8") as f:
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


def test_gemini_user_scope_token_reference(tmp_path, monkeypatch):
    from pathlib import Path
    from dev_tools.handlers import mcp_installer

    assert mcp_installer.HOST_CONFIG_MAP["gemini"] == [
        Path.home() / ".gemini" / "settings.json"
    ]
    config_file = tmp_path / ".gemini" / "settings.json"
    config_file.parent.mkdir()
    config_file.write_text(
        json.dumps({"theme": "dark", "mcpServers": {"other": {"command": "other"}}})
    )
    monkeypatch.setitem(mcp_installer.HOST_CONFIG_MAP, "gemini", [config_file])
    monkeypatch.setenv("GITHUB_TOKEN", "fixture-must-not-be-saved")
    result = detect_and_install_mcp(hosts=["gemini"], dry_run=False)
    assert result["results"][0]["status"] == "updated"
    data = json.loads(config_file.read_text())
    assert data["mcpServers"]["boomtick"] == {
        "command": "boomtick-mcp",
        "env": {"GITHUB_TOKEN": "$GITHUB_TOKEN"},
    }
    assert data["mcpServers"]["other"] == {"command": "other"}
    assert data["theme"] == "dark"
    assert "fixture-must-not-be-saved" not in config_file.read_text()


def test_gemini_dry_run_and_custom_entry_do_not_mutate_defaults(tmp_path, monkeypatch):
    from dev_tools.handlers import mcp_installer

    config_file = tmp_path / "settings.json"
    monkeypatch.setitem(mcp_installer.HOST_CONFIG_MAP, "gemini", [config_file])
    entry = {"command": "custom", "env": {"EXTRA": "$EXTRA"}}
    result = detect_and_install_mcp(hosts=["gemini"], target_config=entry)
    assert result["results"][0]["status"] == "dry_run"
    assert not config_file.exists()
    detect_and_install_mcp(hosts=["gemini"], target_config=entry, dry_run=False)
    assert json.loads(config_file.read_text())["mcpServers"]["boomtick"]["env"] == {
        "GITHUB_TOKEN": "$GITHUB_TOKEN",
        "EXTRA": "$EXTRA",
    }
    assert entry == {"command": "custom", "env": {"EXTRA": "$EXTRA"}}
    assert mcp_installer.DEFAULT_MCP_CONFIG == {"command": "boomtick-mcp"}
