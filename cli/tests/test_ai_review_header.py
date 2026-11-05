# pylint: disable=missing-docstring
import unittest

from dev_tools.handlers.command_handler import CommandHandler


class _FakeGitHub:
    def __init__(self):
        self.posted = []

    def create_review(self, pr_number, body, _findings, event):
        self.posted.append((pr_number, body, event))


class _FakeOrchestrator:
    def __init__(self, recommendation="Approved"):
        self.github = _FakeGitHub()
        self._recommendation = recommendation

    def review_pr(self, pr_number):
        return {
            "prNumber": pr_number,
            "recommendation": self._recommendation,
            "reviewComment": "### Specific Review for PR #1",
            "findings": [],
        }


class TestAiReviewHeader(unittest.TestCase):
    def test_header_discloses_heuristics_not_ai(self):
        # Issue #1113: the posted review is deterministic heuristics —
        # the header must not claim "AI".
        orch = _FakeOrchestrator()
        handler = CommandHandler(orch)
        handler.handle(1, "/ai-review")

        self.assertEqual(len(orch.github.posted), 1)
        _, body, event = orch.github.posted[0]
        self.assertNotIn("AI Code Review", body)
        self.assertIn("heuristic", body.lower())
        self.assertEqual(event, "APPROVE")

    def test_not_approved_maps_to_request_changes(self):
        orch = _FakeOrchestrator(recommendation="Not Approved")
        handler = CommandHandler(orch)
        result = handler.handle(2, "/ai-review")

        self.assertEqual(result["status"], "success")
        _, _, event = orch.github.posted[0]
        self.assertEqual(event, "REQUEST_CHANGES")


if __name__ == "__main__":
    unittest.main()
