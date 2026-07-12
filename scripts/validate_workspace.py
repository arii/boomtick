import json
import sys
import os
from pathlib import Path

def validate_workspace():
    """
    Validates workspace.json against its schema.
    Note: workspace.json is a trusted repository configuration file.
    """
    script_dir = Path(__file__).parent
    workspace_path = script_dir.parent / "workspace.json"
    schema_path = script_dir.parent / "workspace-schema.json"

    if not workspace_path.exists():
        print(f"Error: {workspace_path} not found.")
        sys.exit(1)

    if not schema_path.exists():
        print(f"Error: {schema_path} not found.")
        sys.exit(1)

    try:
        with open(workspace_path, 'r') as f:
            workspace = json.load(f)
        with open(schema_path, 'r') as f:
            schema = json.load(f)
    except Exception as e:
        print(f"Error reading JSON files: {e}")
        sys.exit(1)

    # Basic validation (since we don't want to depend on jsonschema package yet)
    required = schema.get("required", [])
    for field in required:
        if field not in workspace:
            print(f"Error: Missing required field '{field}' in workspace.json")
            sys.exit(1)

    # Validate engines if present in schema
    if "engines" in workspace and "engines" in schema.get("properties", {}):
        engines_schema = schema["properties"]["engines"].get("properties", {})
        for engine in workspace["engines"]:
            if engine not in engines_schema:
                 print(f"Warning: Unknown engine '{engine}' in workspace.json")

    print("workspace.json validated successfully against schema.")

    # Output engines for shell script consumption if requested
    if len(sys.argv) > 1 and sys.argv[1] == "--get-engines":
        print("ENGINES_START")
        print(json.dumps(workspace.get("engines", {})))
        print("ENGINES_END")

if __name__ == "__main__":
    validate_workspace()
