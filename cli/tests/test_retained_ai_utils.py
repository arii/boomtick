"""Compatibility checks for utilities retained during the legacy AI cleanup."""

import json

from dev_tools import utils


def test_downstream_ai_helpers_remain_available():
    # Known downstream experiments import these names directly.
    assert utils.call_ai("offline compatibility probe") is None
    assert utils.clean_llm_output('```json\n{"ok": true}\n```') == '{"ok": true}'


def test_schema_normalization_remains_recursive():
    assert utils.to_standard_schema({"properties": {"x": {"type": "STRING"}}}) == {
        "type": "object",
        "properties": {"x": {"type": "string"}},
    }


def test_existing_usage_receipts_still_count(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    log_dir = utils.get_or_create_log_dir("ai")
    receipt = tmp_path / log_dir / "review-run.jsonl"
    receipt.write_text(json.dumps({"inputTokens": 7, "outputTokens": 3}) + "\n")

    result = utils.verify_ci_metrics(10, 10, 20)

    assert result["status"] == "success"
    assert result["metrics"]["inputTokens"] == 7
    assert result["metrics"]["outputTokens"] == 3
    assert result["metrics"]["totalTokens"] == 10
