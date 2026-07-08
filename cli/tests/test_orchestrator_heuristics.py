import unittest
from dev_tools.orchestrator import Orchestrator
from dev_tools.config import get_config

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
        diff = "+++ b/src/components/Button.tsx\n+<button className=\"px-4\">"
        checks = {"check_runs": []}

        feedback = self.orchestrator.evaluate_pr_heuristics(pr, diff, checks)
        self.assertIn("Design System Anti-patterns", feedback)

    def test_evaluate_pr_heuristics_mixed(self):
        pr = {"number": 3, "head": {"ref": "mixed-branch"}, "title": "Mixed change"}
        diff = "+++ b/setup-agent.sh\n+set -e\n+++ b/src/components/Button.tsx\n+<button className=\"px-4\">"
        checks = {"check_runs": []}

        feedback = self.orchestrator.evaluate_pr_heuristics(pr, diff, checks)
        self.assertIn("Infrastructure/Bootstrap Change", feedback)
        self.assertIn("Design System Anti-patterns", feedback)

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

if __name__ == '__main__':
    unittest.main()
