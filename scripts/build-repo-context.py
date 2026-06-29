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
    # boomtick-pkg -> repo_root
    # We assume we are installed as a subdirectory in the repo
    repo_root = package_root.parent

    # If we are running from a location that isn't boomtick-pkg/scripts,
    # fallback to CWD as repo_root for compatibility
    if package_root.name != "boomtick-pkg":
        repo_root = pathlib.Path(".")
        package_root = repo_root / "boomtick-pkg"

    # 1. Package JSON (Repo Root)
    try:
        package_json_path = repo_root / "package.json"
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
    cli_schema = {}
    try:
        # Dynamically generate cli-schema.json from code
        import click
        cli_dir = os.path.join(package_root, "cli")
        dev_tools_dir = os.path.join(cli_dir, "dev_tools")
        if cli_dir not in sys.path:
            sys.path.append(cli_dir)
        if dev_tools_dir not in sys.path:
            sys.path.append(dev_tools_dir)

        from tdw_services.cli import cli

        def get_type_name(param):
            t = param.type
            if isinstance(t, click.Choice):
                return "choice"
            if hasattr(t, "name"):
                return t.name
            t_str = str(t).lower()
            if "int" in t_str:
                return "integer"
            if "bool" in t_str:
                return "boolean"
            return "string"

        def collect_commands(cmd, prefix=""):
            subcmds = {}
            if isinstance(cmd, click.Group):
                for sub_name, sub_cmd in cmd.commands.items():
                    new_prefix = f"{prefix} {sub_name}".strip()
                    subcmds.update(collect_commands(sub_cmd, new_prefix))
            else:
                cmd_name = prefix
                cmd_help = cmd.help or ""

                args_str = []
                req_args = []
                opt_flags = []
                req_flags = []

                for param in cmd.params:
                    param_type = get_type_name(param)
                    if isinstance(param, click.Argument):
                        arg_name = param.name.upper()
                        if param.nargs == -1:
                            args_str.append(f"<{arg_name}...>")
                        else:
                            args_str.append(f"<{arg_name}>")
                        req_args.append({
                            "name": param.name,
                            "type": param_type,
                            "description": getattr(param, "help", "") or ""
                        })
                    elif isinstance(param, click.Option):
                        flag_name = param.opts[0]
                        flag_desc = param.help or ""
                        option_dict = {
                            "flag": flag_name,
                            "type": param_type,
                            "description": flag_desc
                        }
                        if param.required:
                            req_flags.append(option_dict)
                        else:
                            opt_flags.append(option_dict)

                usage = f"python3 boomtick-pkg/cli/dev_tools/td_cli.py {cmd_name}"
                if req_flags:
                    usage += " " + " ".join([f"{f['flag']} <{f['flag'].lstrip('-').upper()}>" for f in req_flags])
                if opt_flags:
                    usage_parts = []
                    for f in opt_flags:
                        if f['type'] == 'boolean':
                            usage_parts.append(f"{f['flag']}")
                        else:
                            usage_parts.append(f"{f['flag']} <{f['flag'].lstrip('-').upper()}>")
                    usage += " " + " ".join([f"[{u}]" for u in usage_parts])
                if args_str:
                    usage += " " + " ".join(args_str)

                cmd_info = {
                    "description": cmd_help,
                    "exact_usage": usage
                }
                if req_args:
                    cmd_info["required_arguments"] = req_args
                if req_flags:
                    cmd_info["required_flags"] = req_flags
                if opt_flags:
                    cmd_info["optional_flags"] = opt_flags

                subcmds[cmd_name] = cmd_info
            return subcmds

        generated_subcommands = collect_commands(cli)
        cli_schema_path = package_root / "cli" / "dev_tools" / "cli-schema.json"
        
        schema_authority_payload = {
            "tool_name": "td_cli.py",
            "schema_authority": "This file is the single source of truth for td_cli.py. Consult before every CLI call. Takes precedence over examples in AGENTS.md or any agent-specific instruction file.",
            "description": "Custom developer CLI for BoomTick repository management. Do not use interactive menus, and NEVER use the -h or --help flags. Always reference this schema for valid commands.",
            "base_command": "python3 boomtick-pkg/cli/dev_tools/td_cli.py",
            "never_do": [
                "Do not chain subcommands in a single shell call",
                "Do not use --help or -h to discover flags — use this schema",
                "Do not guess flags not listed here",
                "Do not run td_cli.py without checking this schema first",
                "Do not use interactive menus if prompted"
            ],
            "subcommands": generated_subcommands
        }
        
        cli_schema_path.write_text(json.dumps(schema_authority_payload, indent=2))
        cli_schema = schema_authority_payload
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
