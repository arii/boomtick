"""Unit tests for send-jules-impact.py review skip logic."""

import importlib.util
import sys
from pathlib import Path

# Load send-jules-impact.py dynamically
script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "send-jules-impact.py"
spec = importlib.util.spec_from_file_location("send_jules_impact", script_path)
assert spec is not None
assert spec.loader is not None

send_jules_impact = importlib.util.module_from_spec(spec)
sys.modules["send_jules_impact"] = send_jules_impact
spec.loader.exec_module(send_jules_impact)

is_skipped_review = send_jules_impact.is_skipped_review


def test_is_skipped_review_legacy_skipped():
    """Test legacy skipped header format."""
    content = "# PR Review\nSkipped: no changes"
    assert is_skipped_review(content) is True


def test_is_skipped_review_no_files_reviewed():
    """Test '_No files reviewed._' pattern."""
    content = "# PR Review: #123\n\n| File | Findings |\n|---|---|\n\n_No files reviewed._\n"
    assert is_skipped_review(content) is True


def test_is_skipped_review_approved_empty_comments():
    """Test approved recommendation with empty comments array."""
    content = """# PR Review: #123

## Context
- Recommendation: Approved

```json
{
  "recommendation": "Approved",
  "labels": [],
  "comments": []
}
```
"""
    assert is_skipped_review(content) is True


def test_is_skipped_review_approved_with_comments():
    """Test approved recommendation with non-empty comments array."""
    content = """# PR Review: #123

## Context
- Recommendation: Approved

```json
{
  "recommendation": "Approved",
  "labels": [],
  "comments": [
    {
      "path": "src/main.ts",
      "line": 10,
      "body": "[WARN] Minor style issue"
    }
  ]
}
```
"""
    assert is_skipped_review(content) is False


def test_is_skipped_review_changes_requested_empty_comments():
    """Test non-approved recommendation with empty comments array."""
    content = """# PR Review: #123

## Context
- Recommendation: Changes Requested

```json
{
  "recommendation": "Changes Requested",
  "labels": [],
  "comments": []
}
```
"""
    assert is_skipped_review(content) is False
