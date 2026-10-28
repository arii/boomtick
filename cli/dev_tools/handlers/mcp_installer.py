import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional

HOST_CONFIG_MAP = {
    "antigravity": [
        Path.home() / ".gemini" / "antigravity-cli" / "settings.json",
        Path(".gemini/settings.json"),
    ],
    "claude": [
        Path.home() / ".claude.json",
        Path(".claude/mcp.json"),
    ],
    "cursor": [
        Path.home() / ".cursor" / "mcp.json",
        Path(".cursor/mcp.json"),
    ],
    "codex": [
        Path.home() / ".vscode" / "mcp.json",
        Path(".vscode/mcp.json"),
    ],
}

DEFAULT_MCP_CONFIG = {
    "command": "boomtick-mcp"
}


def detect_and_install_mcp(
    hosts: Optional[List[str]] = None,
    dry_run: bool = True,
    target_config: Optional[Dict[str, Any]] = None,
    custom_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Detect agent host environments and register boomtick-mcp into their respective settings.json files.
    """
    mcp_entry = target_config or DEFAULT_MCP_CONFIG
    results = []

    if custom_path:
        target_paths = [Path(custom_path)]
    else:
        target_hosts = hosts if hosts else list(HOST_CONFIG_MAP.keys())
        target_paths = []
        for h in target_hosts:
            if h in HOST_CONFIG_MAP:
                target_paths.extend(HOST_CONFIG_MAP[h])

    for config_path in target_paths:
        path_obj = config_path.expanduser().resolve()

        # Check if parent directory exists or file exists
        file_exists = path_obj.exists()
        parent_exists = path_obj.parent.exists()

        # If parent or file exists, we consider this host target active/eligible
        if file_exists or parent_exists or custom_path:
            status, msg = update_host_config(path_obj, mcp_entry, dry_run=dry_run)
            results.append({
                "path": str(path_obj),
                "status": status,
                "message": msg,
                "exists": file_exists,
            })

    return {
        "status": "success",
        "dry_run": dry_run,
        "results": results,
    }


def update_host_config(
    path_obj: Path,
    mcp_entry: Dict[str, Any],
    dry_run: bool = True,
) -> tuple[str, str]:
    """Reads JSON config at path_obj, updates mcpServers.boomtick, and saves if not dry_run."""
    data: Dict[str, Any] = {}
    if path_obj.exists():
        try:
            with open(path_obj, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    data = json.loads(content)
        except Exception as e:
            return "error", f"Failed to parse existing JSON config at {path_obj}: {str(e)}"

    if not isinstance(data, dict):
        data = {}

    mcp_servers = data.get("mcpServers")
    if not isinstance(mcp_servers, dict):
        mcp_servers = {}

    mcp_servers["boomtick"] = mcp_entry
    data["mcpServers"] = mcp_servers

    if not dry_run:
        try:
            path_obj.parent.mkdir(parents=True, exist_ok=True)
            with open(path_obj, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return "updated", f"Successfully registered boomtick-mcp in {path_obj}"
        except Exception as e:
            return "error", f"Failed to write config to {path_obj}: {str(e)}"
    else:
        return "dry_run", f"Would register boomtick-mcp in {path_obj}"
