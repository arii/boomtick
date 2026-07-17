# pylint: disable=missing-docstring,protected-access,redefined-outer-name
import json
import os
from unittest.mock import MagicMock, patch

import pytest
from dev_tools.services.ai_service import AIClient
from dev_tools.models import AIFileReview, AISynthesisReview


@pytest.fixture
def ai_client():
    with patch("dev_tools.services.ai_service.DependencyGraph"), patch("dev_tools.services.ai_service.VectorStore"):
        client = AIClient()
        return client


def test_estimate_tokens_empty(ai_client):
    assert ai_client._estimate_tokens("") == 0
    assert ai_client._estimate_tokens(None) == 0


def test_estimate_tokens_heuristic(ai_client):
    text = "Hello World!"
    # 12 characters. (12 + 3) // 4 = 3
    assert ai_client._estimate_tokens(text) == 3


@patch("dev_tools.services.ai_service.call_ai")
@patch("dev_tools.services.ai_service.validate_with_model")
def test_generate_code_review_forced_piecemeal(mock_validate, mock_call, ai_client):
    # Mock FORCE_PIECEMEAL_REVIEW env var
    with patch.dict(os.environ, {"FORCE_PIECEMEAL_REVIEW": "true"}):
        pr = {
            "number": 123,
            "title": "Forced Piecemeal PR",
            "checkResults": [],
        }
        diff = (
            "diff --git a/src/App.tsx b/src/App.tsx\n"
            "--- a/src/App.tsx\n"
            "+++ b/src/App.tsx\n"
            "@@ -1,5 +1,6 @@\n"
            "+const a = 1;\n"
        )

        # Mock the AI Client calls
        # 1st call is for chunk review, returns AIFileReview
        # 2nd call is for synthesis review, returns AISynthesisReview
        mock_call.side_effect = ["chunk_response", "synthesis_response"]

        # Mock validation
        chunk_review = {
            "file": "src/App.tsx",
            "issues": [],
            "verdict": "ok",
        }
        synthesis_review = {
            "reviewComment": "Everything looks good!",
            "labels": ["lgtm"],
            "recommendation": "Approved",
        }

        mock_validate.side_effect = [
            (chunk_review, None),       # Validates the chunk review against AIFileReview
            (synthesis_review, None),   # Validates the synthesized review against AISynthesisReview
        ]

        # Mock write_review_file to avoid side effects
        ai_client._write_review_file = MagicMock()

        res = ai_client.generate_code_review(pr, diff)

        # Assert results
        assert res["recommendation"] == "Approved"
        assert res["reviewComment"] == "Everything looks good!"
        assert res["labels"] == ["lgtm"]

        # Ensure correct models/schemas were called
        assert mock_call.call_count == 2
        # First call: schema should be AIFileReview's schema
        first_call_schema = mock_call.call_args_list[0][1]["schema"]
        assert first_call_schema == AIFileReview.model_json_schema()

        # Second call (synthesis): does not use schema mode (schema=None/not provided)
        assert mock_call.call_args_list[1][1].get("schema") is None


@patch("dev_tools.services.ai_service.call_ai")
@patch("dev_tools.services.ai_service.validate_with_model")
def test_generate_code_review_chunk_failure(mock_validate, mock_call, ai_client):
    with patch.dict(os.environ, {"FORCE_PIECEMEAL_REVIEW": "true"}):
        pr = {
            "number": 456,
            "title": "Failed Chunk PR",
            "checkResults": [],
        }
        diff = (
            "diff --git a/src/App.tsx b/src/App.tsx\n"
            "--- a/src/App.tsx\n"
            "+++ b/src/App.tsx\n"
            "@@ -1,5 +1,6 @@\n"
            "+const a = 1;\n"
        )

        # Simulate chunk AI call failing/returning empty response
        # It retries _MAX_AI_RETRIES (3) times, then fails.
        # Then synthesis call follows.
        mock_call.side_effect = [None, None, None, "synthesis_response"]

        synthesis_review = {
            "reviewComment": "Proceeding with caution.",
            "labels": ["needs-changes"],
            "recommendation": "Not Approved",
        }
        mock_validate.return_value = (synthesis_review, None)

        ai_client._write_review_file = MagicMock()

        res = ai_client.generate_code_review(pr, diff)

        # Confirm synthesis proceeded despite chunk review failure
        assert res["recommendation"] == "Not Approved"
        assert res["reviewComment"] == "Proceeding_with_caution." or res["reviewComment"] == "Proceeding with caution."

        # Ensure write_review_file was called with the failed chunk status
        ai_client._write_review_file.assert_called_once()
        passed_file_reviews = ai_client._write_review_file.call_args[0][4]
        assert len(passed_file_reviews) == 1
        assert passed_file_reviews[0]["verdict"] == "error"
        assert "Failed to get a parseable review" in passed_file_reviews[0]["error"]
