# pylint: disable=missing-docstring,unused-argument,protected-access
import json
from unittest.mock import patch

from dev_tools.services.ai_service import AIClient

# A realistic unified diff that parse_diff_into_file_chunks will consider reviewable
REALISTIC_DIFF_1 = (
    "diff --git a/src/main.ts b/src/main.ts\n"
    "index 0000000..e69de29 100644\n"
    "--- a/src/main.ts\n"
    "+++ b/src/main.ts\n"
    "@@ -1,3 +1,4 @@\n"
    " const x = 1;\n"
    "+console.log('hello');\n"
    " const y = 2;"
)

REALISTIC_DIFF_2 = (
    "diff --git a/src/main.ts b/src/main.ts\n"
    "index 0000000..e69de29 100644\n"
    "--- a/src/main.ts\n"
    "+++ b/src/main.ts\n"
    "@@ -1,3 +1,4 @@\n"
    " const x = 1;\n"
    "+export class MainArch {}\n"
    " const y = 2;"
)

@patch("dev_tools.services.ai_service.call_ai")
def test_generate_code_review_triage_bypass_specialist(mock_call_ai):
    # Mock triage to say NO specialist needed, and return fast feedback
    triage_payload = {
        "needsSpecialistReview": False,
        "reason": "Very simple change, no complex architecture or vulnerabilities detected.",
        "fastFeedback": "The changes look clean and well-structured. No issues found."
    }

    # Wrap in triage_result tags
    triage_xml = f"<triage_result>\n{json.dumps(triage_payload)}\n</triage_result>"

    # Configure mock
    mock_call_ai.return_value = triage_xml

    client = AIClient()
    pr_details = {
        "number": 123,
        "title": "Minor formatting fix",
        "checkResults": []
    }

    # We need to mock _write_review_file to avoid actual disk writes during tests
    with patch.object(client, "_write_review_file") as mock_write_file:
        res = client.generate_code_review(pr_details, REALISTIC_DIFF_1)

        # Verify results
        assert res["recommendation"] == "Approved"
        assert "The changes look clean" in res["reviewComment"]
        assert res["labels"] == ["lgtm"]

        # Verify call_ai was called once (for triage only), bypassing specialist/piecemeal review
        assert mock_call_ai.call_count == 1
        mock_write_file.assert_called_once()


@patch("dev_tools.services.ai_service.call_ai")
def test_generate_code_review_triage_triggers_specialist(mock_call_ai):
    # Mock triage to say YES specialist is needed
    triage_payload = {
        "needsSpecialistReview": True,
        "reason": "Complex architectural changes found.",
        "fastFeedback": ""
    }
    triage_xml = f"<triage_result>\n{json.dumps(triage_payload)}\n</triage_result>"

    # Special review result for the next call_ai
    special_review_result = {
        "file_reviews": [
            {
                "file": "src/main.ts",
                "issues": [],
                "verdict": "ok"
            }
        ],
        "reviewComment": "Detailed review complete.",
        "labels": ["lgtm"],
        "recommendation": "Approved"
    }
    special_xml = f"<findings>\n{json.dumps(special_review_result)}\n</findings>"

    # Mock call_ai returns triage_xml on first call, special_xml on second call
    mock_call_ai.side_effect = [triage_xml, special_xml]

    client = AIClient()
    pr_details = {
        "number": 123,
        "title": "Major Architectural Update",
        "checkResults": []
    }

    with patch.object(client, "_write_review_file") as mock_write_file:
        res = client.generate_code_review(pr_details, REALISTIC_DIFF_2)

        # Verify results
        assert res["recommendation"] == "Approved"
        assert "Detailed review complete" in res["reviewComment"]

        # Verify call_ai was called twice: once for triage, once for specialist review
        assert mock_call_ai.call_count == 2
        mock_write_file.assert_called_once()


@patch("dev_tools.services.ai_service.call_ai")
def test_process_piecemeal_review_parallel_execution(mock_call_ai):
    # Setup multiple reviewable chunks
    reviewable = [
        {"file": "src/file1.ts", "chunk_index": 0, "diff_text": "diff1", "added_lines": 5, "skip": False},
        {"file": "src/file2.ts", "chunk_index": 0, "diff_text": "diff2", "added_lines": 10, "skip": False},
        {"file": "src/file3.ts", "chunk_index": 0, "diff_text": "diff3", "added_lines": 15, "skip": False},
    ]
    chunks = reviewable

    # Setup mock responses for chunk reviews
    chunk_responses = []
    for chunk in reviewable:
        resp = {
            "file": chunk["file"],
            "issues": [],
            "verdict": "ok"
        }
        chunk_responses.append(f"<findings>\n{json.dumps(resp)}\n</findings>")

    # Mock response for summary synthesis (after chunks are processed)
    synthesis_resp = {
        "recommendation": "Approved",
        "labels": ["lgtm"],
        "reviewComment": "All chunks passed."
    }
    chunk_responses.append(f"<findings>\n{json.dumps(synthesis_resp)}\n</findings>")

    mock_call_ai.side_effect = chunk_responses

    client = AIClient()
    pr_details = {
        "number": 123,
        "title": "Piecemeal Review",
        "checkResults": []
    }

    # Patch progress snapshot and review file writer to prevent side effects
    with patch.object(client, "_write_progress_snapshot") as mock_progress, \
         patch.object(client, "_write_review_file") as mock_write_file, \
         patch.object(client, "_synthesize_review", return_value=synthesis_resp):

        res = client._process_piecemeal_review(
            reviewable=reviewable,
            pr_num=123,
            pr_title="Piecemeal Review",
            checks_summary="No checks.",
            chunks=chunks,
            pr=pr_details,
            has_ci_failures=False,
            ci_failures=[],
            failing_names="none",
            estimated_tokens=30000
        )

        # Check final output
        assert res["recommendation"] == "Approved"
        assert res["reviewComment"] == "All chunks passed."

        # Verify concurrent progress updates were recorded
        assert mock_progress.call_count == 3
        assert mock_write_file.call_count == 1
