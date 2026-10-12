# pylint: disable=missing-docstring
import json

from unittest.mock import MagicMock
from dev_tools.models import AIFullReview, AIReviewIssue, AISynthesisReview
from dev_tools.services.ai_service import AIClient, _get_review_prompt_constants, validate_with_model


def test_validate_ai_review_issue_success():
    data = {
        "id": "1",
        "severity": "error",
        "comment": "test comment",
        "confidence": "high",
        "line": 10,
    }
    parsed, err = validate_with_model(data, AIReviewIssue)
    assert err is None
    assert parsed["comment"] == "test comment"
    assert parsed["severity"] == "error"


def test_validate_ai_review_issue_alternative_field():
    data = {"severity": "warn", "issue": "test issue", "confidence": "medium"}
    parsed, err = validate_with_model(data, AIReviewIssue)
    assert err is None
    assert parsed["issue"] == "test issue"


def test_validate_ai_review_issue_failure_missing_fields():
    data = {
        "severity": "error",
        "confidence": "high",
        # missing both issue and comment
    }
    parsed, err = validate_with_model(data, AIReviewIssue)
    assert parsed is None
    assert "issue" in err or "comment" in err


def test_validate_ai_review_issue_failure_invalid_enum():
    data = {
        "severity": "critical",  # invalid
        "comment": "test",
        "confidence": "very high",  # invalid
    }
    parsed, err = validate_with_model(data, AIReviewIssue)
    assert parsed is None
    assert "severity" in err
    assert "confidence" in err


def test_validate_full_review_success():
    data = {
        "file_reviews": [
            {
                "file": "test.py",
                "issues": [{"severity": "info", "comment": "nit", "confidence": "low", "line": 1}],
                "verdict": "ok",
            }
        ],
        "reviewComment": "Looks good",
        "labels": ["lgtm"],
        "recommendation": "Approved",
    }
    parsed, err = validate_with_model(data, AIFullReview)
    assert err is None
    assert len(parsed["file_reviews"]) == 1
    assert parsed["recommendation"] == "Approved"


def test_validate_synthesis_review_double_encoding():
    # Simulate double stringified JSON
    inner_json = json.dumps({"reviewComment": "Summary", "labels": [], "recommendation": "Not Approved"})
    double_encoded = json.dumps(inner_json)

    parsed, err = validate_with_model(double_encoded, AISynthesisReview)
    assert err is None
    assert parsed["recommendation"] == "Not Approved"


def test_validate_with_model_detailed_errors():
    data = {
        "file_reviews": [
            {
                "file": "test.py",
                "issues": [
                    {
                        "severity": "invalid",
                        "confidence": "low",
                        # missing issue/comment
                    }
                ],
                "verdict": "ok",
            }
        ],
        "reviewComment": "oops",
        "labels": [],
        "recommendation": "Approved",
    }
    parsed, err = validate_with_model(data, AIFullReview)
    assert parsed is None
    # Check that error message contains the path to the error
    assert "file_reviews -> 0 -> issues -> 0 -> severity" in err
    assert "file_reviews -> 0 -> issues -> 0" in err


def test_ai_client_custom_sleep_fn():
    mock_sleep = MagicMock()
    client = AIClient(sleep_fn=mock_sleep)
    assert client.sleep_fn == mock_sleep

    # Verify sleep_fn is invoked when a review attempt fails
    client.call_ai = MagicMock(return_value="invalid json text")
    client._execute_single_pass_review("test prompt", 1, 101)
    assert mock_sleep.call_count > 0


def test_get_review_prompt_constants_content_validation():
    json_rules, snippet_rules, common_rules = _get_review_prompt_constants()
    assert "Strict JSON Verification" in json_rules
    assert "STRICT SNIPPET RULE" in snippet_rules
    assert "CONTENT VALIDATION RULE" in common_rules
    assert "DEFAULT SKEPTICAL STANCE" in common_rules
    assert "BLOCK" in common_rules


def test_resolve_file_conflicts_deterministic_strategies(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr("os.getcwd", lambda: str(Path(tmp_path).resolve()))

    conflict_file = tmp_path / "test.txt"
    content = (
        "line 1\n"
        "<<<<<<< HEAD\n"
        "ours 1\n"
        "ours 2\n"
        "=======\n"
        "theirs 1\n"
        ">>>>>>> branch\n"
        "line 2\n"
    )
    conflict_file.write_text(content, encoding="utf-8")

    client = AIClient()

    # Test 'ours' strategy
    res = client.resolve_file_conflicts(str(conflict_file), strategy="ours")
    assert res is True
    assert conflict_file.read_text(encoding="utf-8") == "line 1\nours 1\nours 2\nline 2\n"

    # Reset file and test 'theirs' strategy
    conflict_file.write_text(content, encoding="utf-8")
    res = client.resolve_file_conflicts(str(conflict_file), strategy="theirs")
    assert res is True
    assert conflict_file.read_text(encoding="utf-8") == "line 1\ntheirs 1\nline 2\n"

    # Reset file and test 'union' strategy
    conflict_file.write_text(content, encoding="utf-8")
    res = client.resolve_file_conflicts(str(conflict_file), strategy="union")
    assert res is True
    assert conflict_file.read_text(encoding="utf-8") == "line 1\nours 1\nours 2\ntheirs 1\nline 2\n"


def test_resolve_file_conflicts_hunk_scoped_and_ai_fallback(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr("os.getcwd", lambda: str(Path(tmp_path).resolve()))

    conflict_file = tmp_path / "large_doc.md"
    padding_before = "\n".join(f"Line before {i}" for i in range(30))
    padding_after = "\n".join(f"Line after {i}" for i in range(30))

    content = f"{padding_before}\n<<<<<<< HEAD\nresolved AI line\n=======\nold line\n>>>>>>> branch\n{padding_after}\n"
    conflict_file.write_text(content, encoding="utf-8")

    client = AIClient()

    # Mock generate to simulate successful hunk-scoped response
    prompts_captured = []

    def mock_generate(prompt, **kwargs):
        prompts_captured.append(prompt)
        return "resolved AI line\n"

    monkeypatch.setattr(client, "generate", mock_generate)

    res = client.resolve_file_conflicts(str(conflict_file))
    assert res is True
    assert len(prompts_captured) == 1
    assert "Resolve this specific Git merge conflict hunk" in prompts_captured[0]
    assert "SURROUNDING PRE-CONTEXT:" in prompts_captured[0]
    assert "<<<<<<< OURS" in prompts_captured[0]
    resolved_text = conflict_file.read_text(encoding="utf-8")
    assert "resolved AI line" in resolved_text
    assert "<<<<<<<" not in resolved_text

    # Test fallback to ours when generate raises exception
    conflict_file.write_text(content, encoding="utf-8")

    def mock_failing_generate(prompt, **kwargs):
        raise RuntimeError("API limit exceeded")

    monkeypatch.setattr(client, "generate", mock_failing_generate)

    res_fallback = client.resolve_file_conflicts(str(conflict_file))
    assert res_fallback is True
    fallback_text = conflict_file.read_text(encoding="utf-8")
    assert "resolved AI line" in fallback_text
    assert "<<<<<<<" not in fallback_text


def test_call_gemini_retry_and_timeout(monkeypatch):
    import os
    client = AIClient()
    monkeypatch.setattr(client, "gemini_api_key", "mock-gemini-key")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "45")

    mock_retry = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "gemini output"}]}}]
    }
    mock_retry.return_value = mock_response

    monkeypatch.setattr("dev_tools.utils._call_api_with_retry", mock_retry)

    result = client.call_gemini("test prompt")
    assert result == "gemini output"
    mock_retry.assert_called_once()
    assert mock_retry.call_args[1]["timeout"] == 45
    assert mock_retry.call_args[1]["max_retries"] == 3


def test_generate_provider_error_message(monkeypatch):
    client = AIClient()
    monkeypatch.setattr(client, "call_ai", lambda *args, **kwargs: None)

    try:
        client.generate("test prompt")
        assert False, "Should have raised EnvironmentError"
    except EnvironmentError as e:
        assert "No AI service available (OpenAI and Gemini failed or are unavailable)." in str(e)
