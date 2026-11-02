# pylint: disable=consider-using-from-import,import-outside-toplevel,missing-docstring,invalid-name,wrong-import-position
import inspect
import json
import os
import sys

from dev_tools import models
from pydantic import BaseModel


def get_models_schema():
    schemas = {}
    for name, obj in inspect.getmembers(models):
        if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj is not BaseModel:
            # Skip base classes if any
            if name in ("CLIResponse", "CLIInput"):
                continue
            # Force export using camelCase aliases
            schemas[name] = obj.model_json_schema(by_alias=True)
    return schemas


def generate_schema():
    """Generates the Pydantic models schema contract.

    Sole owner/writer of cli/dev_tools/cli-schema.json.
    Command schemas are owned separately by cli-commands-schema.json.
    """
    schemas = {
        "_warning": "AUTO-GENERATED: DO NOT EDIT MANUALLY. Update models.py instead.",
        "models": get_models_schema(),
    }

    # Use cli-schema.json as the models target (sole writer: schema_gen.py)
    # Written cleanly every time (no merge with existing content):
    # stale keys from older writers must never survive regeneration.
    output_path = os.path.join(os.path.dirname(__file__), "cli-schema.json")
    tmp_path = output_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(schemas, f, indent=2)
        f.write("\n")
    os.replace(tmp_path, output_path)

    print(
        f"Updated cli-schema.json with {len(schemas['models'])} models at {output_path}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    generate_schema()
