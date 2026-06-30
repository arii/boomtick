import json
import os
from dev_tools.models import (
    CreateIssueInput, SearchPRsInput, IssueUpdateInput,
    CreateIssueResponse, SearchPRsResponse, IssueUpdateResponse
)

def get_models_schema():
    return {
        "CreateIssueInput": CreateIssueInput.model_json_schema(),
        "SearchPRsInput": SearchPRsInput.model_json_schema(),
        "IssueUpdateInput": IssueUpdateInput.model_json_schema(),
        "CreateIssueResponse": CreateIssueResponse.model_json_schema(),
        "SearchPRsResponse": SearchPRsResponse.model_json_schema(),
        "IssueUpdateResponse": IssueUpdateResponse.model_json_schema(),
    }

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

    print(f"Updated cli-schema.json with models at {output_path}")

if __name__ == "__main__":
    generate_schema()
