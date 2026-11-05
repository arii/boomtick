# pylint: disable=missing-docstring
import unittest

from dev_tools.config import get_config
from dev_tools.orchestrator import Orchestrator


class TestOrchestratorHeuristics(unittest.TestCase):
    def setUp(self):
        self.orchestrator = Orchestrator()
        self.config = get_config()

    def test_evaluate_pr_heuristics_infra(self):
        pr = {"number": 1, "head": {"ref": "infra-branch"}, "title": "Infra change"}
        # Diff touching an infra file
        diff = "+++ b/setup-agent.sh\n+set -e"
        checks = {"check_runs": []}

        feedback = self.orchestrator.evaluate_pr_heuristics(pr, diff, checks)
        self.assertIn("Infrastructure/Bootstrap Change", feedback)
        self.assertIn("set -e", feedback)

    def test_evaluate_pr_heuristics_ui(self):
        pr = {"number": 2, "head": {"ref": "ui-branch"}, "title": "UI change"}
        # Diff touching a UI file
        diff = '+++ b/src/components/Button.tsx\n+<button className="px-4">'
        checks = {"check_runs": []}

        feedback = self.orchestrator.evaluate_pr_heuristics(pr, diff, checks)
        self.assertIn("Design System Anti-patterns", feedback)

    def test_evaluate_pr_heuristics_mixed(self):
        pr = {"number": 3, "head": {"ref": "mixed-branch"}, "title": "Mixed change"}
        diff = '+++ b/setup-agent.sh\n+set -e\n+++ b/src/components/Button.tsx\n+<button className="px-4">'
        checks = {"check_runs": []}

        feedback = self.orchestrator.evaluate_pr_heuristics(pr, diff, checks)
        self.assertIn("Infrastructure/Bootstrap Change", feedback)
        self.assertIn("Design System Anti-patterns", feedback)

    def test_no_tailwind_finding_for_plain_css(self):
        # Issue #1113: `display: flex` / grid in a plain stylesheet is not
        # Tailwind usage — the primitives advisory must not fire.
        pr = {"number": 5, "head": {"ref": "css-branch"}, "title": "CSS tweak"}
        diff = (
            "+++ b/frontend/src/index.css\n"
            "@@ -1,2 +1,3 @@\n"
            " .row { display: flex; }\n"
            "+.grid { display: grid; }\n"
            "+.spacer { margin-top: 8px; }"
        )
        checks = {"check_runs": []}

        feedback = self.orchestrator.evaluate_pr_heuristics(pr, diff, checks)
        self.assertNotIn("Design System Anti-patterns", feedback)

    def test_no_tailwind_finding_for_removed_lines(self):
        # Issue #1113: utility classes only on removed (`-`) lines are not
        # evidence of Tailwind usage in the PR.
        pr = {"number": 6, "head": {"ref": "cleanup-branch"}, "title": "Drop legacy"}
        diff = (
            "+++ b/src/components/Button.tsx\n"
            "@@ -1,2 +1,1 @@\n"
            + "-<button className=\"px-4 flex\">\n"
            + "+<button>"
        )
        checks = {"check_runs": []}

        feedback = self.orchestrator.evaluate_pr_heuristics(pr, diff, checks)
        self.assertNotIn("Design System Anti-patterns", feedback)

    def test_tailwind_finding_cites_diff_hunk(self):
        # Issue #1113: real Tailwind usage still fires, and the finding
        # cites the file plus the added line as evidence.
        pr = {"number": 7, "head": {"ref": "tw-branch"}, "title": "Tailwind card"}
        diff = (
            "+++ b/src/components/Card.tsx\n"
            "@@ -1,1 +1,1 @@\n"
            + "-<div className=\"card\">\n"
            + "+<div className=\"px-4 flex\">"
        )
        checks = {"check_runs": []}

        feedback = self.orchestrator.evaluate_pr_heuristics(pr, diff, checks)
        self.assertIn("Design System Anti-patterns", feedback)
        self.assertIn("src/components/Card.tsx", feedback)
        self.assertIn("px-4 flex", feedback)

        findings = self.orchestrator.collect_pr_findings(pr, diff, checks)
        tw = [f for f in findings if f["rule"] == "tailwind-primitives"]
        self.assertEqual(len(tw), 1)
        self.assertEqual(tw[0]["file"], "src/components/Card.tsx")
        self.assertTrue(any("px-4 flex" in line for line in tw[0]["evidence"]))

    def test_evaluate_pr_heuristics_temp_files(self):
        pr = {"number": 4, "head": {"ref": "temp-files-branch"}, "title": "Added some logs"}
        # Diff adding suspicious files
        diff = "+++ b/workflow-audit-status.md\n+Some findings\n+++ b/package.json\n+{}\n+++ b/data-dump.json"
        checks = {"check_runs": []}

        feedback = self.orchestrator.evaluate_pr_heuristics(pr, diff, checks)
        self.assertIn("Stray/Temporary Files", feedback)
        self.assertIn("workflow-audit-status.md", feedback)
        self.assertIn("data-dump.json", feedback)
        # Should NOT flag package.json
        self.assertNotIn("package.json", feedback)


if __name__ == "__main__":
    unittest.main()
