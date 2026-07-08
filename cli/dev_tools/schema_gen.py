import json
import os
import inspect
from pydantic import BaseModel
import dev_tools.models as models

def get_models_schema():
    schemas = {}
    for name, obj in inspect.getmembers(models):
        if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj is not BaseModel:
            # Skip base classes if any
            if name in ("CLIResponse", "CLIInput"):
                continue
            # Force export using field names (camelCase) instead of aliases (snake_case)
            schemas[name] = obj.model_json_schema(by_alias=False)
    return schemas

def generate_schema():
    schemas = {
        "_warning": "AUTO-GENERATED: DO NOT EDIT MANUALLY. Update models.py instead.",
        "models": get_models_schema()
    }

    # Use cli-schema.json as the unified target
    output_path = os.path.join(os.path.dirname(__file__), "cli-schema.json")

    # Read existing if exists to merge
    existing = {}
    if os.path.exists(output_path):
        try:
            with open(output_path, "r") as f:
                existing = json.load(f)
        except Exception as e:
            print(f"Warning: Could not read existing cli-schema.json: {e}")

    existing.update(schemas)

    with open(output_path, "w") as f:
        json.dump(existing, f, indent=2)
        f.write("\n")

    import sys
    print(f"Updated cli-schema.json with {len(schemas['models'])} models at {output_path}", file=sys.stderr)

if __name__ == "__main__":
    generate_schema()
