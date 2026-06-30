#!/usr/bin/env python3
import json
import pathlib
import sys
import os

def build_repo_context():
    """Gathers static context about the repository."""

    # 1. Environment Discovery
    # We identify the package_root by the location of this script
    script_path = pathlib.Path(__file__).resolve()
    # scripts/build-repo-context.py -> package_root
    package_root = script_path.parent.parent

    # Robust Detection: check for the monolithic marker ('src' dir at repo root)
    # If the parent directory contains 'src/', we are in the monorepo.
    # Otherwise, we are at the root of a standalone extracted repo.
    if (package_root.parent / "src").exists():
        repo_root = package_root.parent
        is_standalone = False
    else:
        repo_root = package_root
        is_standalone = True

    # 2. Package JSON (Repo Root)
    try:
        package_json_path = repo_root / "package.json"
        if not package_json_path.exists() and is_standalone:
             # Fallback for some environments where we might be running from within a subfolder
             package_json_path = pathlib.Path("package.json").resolve()

        package_json = json.loads(package_json_path.read_text())
        package_summary = {
            "name": package_json.get("name"),
            "scripts": package_json.get("scripts", {}),
            "dependencies": sorted(list(package_json.get("dependencies", {}).keys())),
            "devDependencies": sorted(list(package_json.get("devDependencies", {}).keys())),
        }
    except Exception as e:
        print(f"Error reading package.json from {repo_root}: {e}", file=sys.stderr)
        package_summary = {}

    # 3. Project Config (Repo Root)
    project_config = {}
    try:
        project_config_path = repo_root / "project_config.json"
        if project_config_path.exists():
            project_config = json.loads(project_config_path.read_text())
    except Exception as e:
        print(f"Error reading project_config.json: {e}", file=sys.stderr)

    # 4. MCP Schema (Package Internal)
    mcp_schema = {"tools": [], "prompts": [], "resources": []}
    try:
        import subprocess
        mcp_dir = package_root / "mcp"
        if mcp_dir.exists():
            result = subprocess.run(
                ["npx", "tsx", "scripts/export-mcp-schema.ts"],
                cwd=str(mcp_dir),
                capture_output=True,
                text=True,
                check=True
            )
            mcp_schema = json.loads(result.stdout)
    except Exception as e:
        print(f"Error gathering MCP schema: {e}", file=sys.stderr)

    # 5. CLI Schema (Package Internal)
    cli_schema = {}
    try:
        cli_schema_path = package_root / "cli" / "dev_tools" / "cli-schema.json"
        if cli_schema_path.exists():
            cli_schema = json.loads(cli_schema_path.read_text())
    except Exception as e:
        print(f"Error reading cli-schema.json: {e}", file=sys.stderr)

    # 6. File Tree (Repo Root)
    def get_dir_structure(path, max_depth=2, current_depth=0):
        if current_depth >= max_depth:
            return "..."
        structure = {}
        try:
            for item in sorted(path.iterdir()):
                if item.name.startswith('.') or item.name == 'node_modules' or item.name == '__pycache__':
                    continue
                if item.is_dir():
                    structure[item.name + '/'] = get_dir_structure(item, max_depth, current_depth + 1)
                else:
                    structure[item.name] = None
        except Exception:
            pass
        return structure

    file_tree = get_dir_structure(repo_root)

    # Assemble context
    return {
        "repo": {
             "name": package_summary.get("name", "Unknown Repo"),
             "standalone": is_standalone
        },
        "package_json": package_summary,
        "project_config": project_config,
        "mcp_schema": mcp_schema,
        "cli_schema": cli_schema,
        "file_tree": file_tree,
    }

if __name__ == "__main__":
    try:
        context = build_repo_context()
        print(json.dumps(context, indent=2, sort_keys=True))
    except Exception as e:
        print(f"FATAL: Context generation failed: {e}", file=sys.stderr)
        sys.exit(1)
