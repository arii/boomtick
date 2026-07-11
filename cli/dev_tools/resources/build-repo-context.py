#!/usr/bin/env python3
import json
import pathlib
import sys
import os

def build_repo_context():
    """Gathers static context about the repository."""

    # Discovery: find the repo root and package root
    script_path = pathlib.Path(__file__).resolve()
    # boomtick-pkg/scripts/build-repo-context.py -> boomtick-pkg
    package_root = script_path.parent.parent

    # Check if we are in a monorepo or a standalone repo
    if (package_root.parent / "package.json").exists() and (package_root.parent / "boomtick-pkg").exists():
        # Monorepo mode
        repo_root = package_root.parent
    else:
        # Standalone mode
        repo_root = package_root

    # If we are running from a location that isn't boomtick-pkg/scripts,
    # fallback to discovery based on workspace.json
    if package_root.name != "boomtick-pkg" or not (package_root / "workspace.json").exists():
        # Search upwards for workspace.json using Path.parents
        found_pkg = False
        for parent in script_path.parents:
            if (parent / "workspace.json").exists():
                package_root = parent
                found_pkg = True
                break

        if found_pkg:
            if (package_root.parent / "package.json").exists() and (package_root.parent / "boomtick-pkg").exists():
                repo_root = package_root.parent
            else:
                repo_root = package_root
        else:
            # Absolute fallback
            repo_root = pathlib.Path(".").resolve()
            package_root = repo_root if (repo_root / "workspace.json").exists() else repo_root / "boomtick-pkg"

    # 1. Package JSON (Repo Root)
    try:
        package_json_path = repo_root / "package.json"
        if not package_json_path.exists() and (repo_root / "workspace.json").exists():
            # In extracted standalone mode, use workspace.json as the package authority
            package_json_path = repo_root / "workspace.json"

        package_json = json.loads(package_json_path.read_text())
        # simplify package.json to the most important parts for context
        package_summary = {
            "name": package_json.get("name"),
            "scripts": package_json.get("scripts", {}),
            "dependencies": sorted(list(package_json.get("dependencies", {}).keys())),
            "devDependencies": sorted(list(package_json.get("devDependencies", {}).keys())),
        }
    except Exception as e:
        print(f"Error reading package.json: {e}", file=sys.stderr)
        package_summary = {}

    # 2. Project Config (Repo Root)
    project_config = {}
    try:
        project_config_path = repo_root / "project_config.json"
        if project_config_path.exists():
            project_config = json.loads(project_config_path.read_text())
    except Exception as e:
        print(f"Error reading project_config.json: {e}", file=sys.stderr)

    # 3. MCP Schema (Package Internal)
    mcp_schema = {"tools": [], "prompts": [], "resources": []}
    try:
        import subprocess
        mcp_dir = package_root / "mcp"
        if mcp_dir.exists():
            # Use npx tsx to run the export script without needing to compile it
            # We run it from the mcp_dir to ensure it finds its own local config
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

    # 4. CLI Schema (Package Internal)
    cli_schema = {
        "tool_name": "td-cli",
        "schema_authority": "Use 'repo.get_command_schema' or 'td-cli schema <path>' for granular discovery. This file remains for legacy fallback.",
        "description": "Custom developer CLI for BoomTick repository management.",
        "base_command": "td-cli"
    }
    try:
        from dev_tools.cli import cli
        from dev_tools.schema_utils import collect_commands

        # We keep cli-schema.json updated but minimal for the aggregate context
        generated_subcommands = collect_commands(cli, max_depth=1)
        cli_schema["subcommands"] = generated_subcommands
        
        cli_schema_path = package_root / "cli" / "dev_tools" / "cli-schema.json"
        
        # Write full schema for legacy/reference but don't bloat the agent context
        full_subcommands = collect_commands(cli)
        full_payload = cli_schema.copy()
        full_payload["subcommands"] = full_subcommands
        cli_schema_path.write_text(json.dumps(full_payload, indent=2))

        # Also trigger Pydantic model contract generation
        try:
            from dev_tools.schema_gen import generate_schema
            import io
            from contextlib import redirect_stdout
            # Capture stdout to ensure clean JSON output for build-repo-context.py
            with redirect_stdout(io.StringIO()):
                generate_schema()
            # Note: sync-contracts.ts is run via pnpm run verify:schemas or manually
        except Exception as schema_err:
            print(f"Error generating model schemas: {schema_err}", file=sys.stderr)

    except Exception as e:
        print(f"Error generating cli-schema.json dynamically: {e}", file=sys.stderr)
        # Fallback to reading file if generation failed
        try:
            cli_schema_path = package_root / "cli" / "dev_tools" / "cli-schema.json"
            if cli_schema_path.exists():
                cli_schema = json.loads(cli_schema_path.read_text())
        except Exception as read_err:
            print(f"Fallback read of cli-schema.json failed: {read_err}", file=sys.stderr)

    # 5. File Tree (Repo Root)
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
        if not context.get("package_json"):
            raise ValueError("Failed to gather basic repository context (package.json missing or invalid)")
        # sort_keys=True ensures the output is deterministic for revision control
        print(json.dumps(context, indent=2, sort_keys=True))
    except Exception as e:
        print(f"FATAL: Context generation failed: {e}", file=sys.stderr)
        sys.exit(1)
