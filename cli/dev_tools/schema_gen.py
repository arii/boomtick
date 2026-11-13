# pylint: disable=consider-using-from-import,import-outside-toplevel,missing-docstring,invalid-name,wrong-import-position
import inspect
import json
import os
import sys

from dev_tools import models
from pydantic import BaseModel


def _unwrap_optional_null(prop):
    """Unwrap pydantic's `anyOf: [T, null]` optional rendering to just T.

    `Optional[T] = None` fields render on the wire as anyOf [T, null] with
    "default": null, which advertises explicit-null acceptance while the
    generated runtime Zod only accepts omission (the source of the
    documented "never pass null" footgun). Emitting T alone keeps the wire
    schema and runtime Zod in agreement: optional means omit, never null.
    """
    if not isinstance(prop, dict) or "anyOf" not in prop:
        return prop
    branches = [b for b in prop["anyOf"] if isinstance(b, dict)]
    null_branches = [b for b in branches if b.get("type") == "null"]
    non_null = [b for b in branches if b.get("type") != "null"]
    if not null_branches:
        return prop
    merged = dict(non_null[0]) if len(non_null) == 1 else {"anyOf": non_null}
    if "description" in prop:
        merged["description"] = prop["description"]
    if prop.get("default") is not None:
        merged["default"] = prop["default"]
    return merged


def _strip_input_null_branches(schema):
    if not isinstance(schema, dict):
        return
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for key, prop in properties.items():
            properties[key] = _unwrap_optional_null(prop)
    sub_defs = schema.get("$defs")
    if isinstance(sub_defs, dict):
        for sub in sub_defs.values():
            _strip_input_null_branches(sub)


def get_models_schema():
    schemas = {}
    for name, obj in inspect.getmembers(models):
        if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj is not BaseModel:
            # Skip base classes if any
            if name in ("CLIResponse", "CLIInput"):
                continue
            # Force export using camelCase aliases
            schema = obj.model_json_schema(by_alias=True)
            if name.endswith("Input"):
                _strip_input_null_branches(schema)
            schemas[name] = schema
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
