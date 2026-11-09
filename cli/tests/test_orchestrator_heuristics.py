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
            "@@ -1,2 +1,1 @@\n" + '-<button className="px-4 flex">\n' + "+<button>"
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
            + '-<div className="card">\n'
            + '+<div className="px-4 flex">'
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
        pr = {
            "number": 4,
            "head": {"ref": "temp-files-branch"},
            "title": "Added some logs",
        }
        # Diff adding suspicious files
        diff = "+++ b/workflow-audit-status.md\n+Some findings\n+++ b/package.json\n+{}\n+++ b/data-dump.json"
        checks = {"check_runs": []}

        feedback = self.orchestrator.evaluate_pr_heuristics(pr, diff, checks)
        self.assertIn("Stray/Temporary Files", feedback)
        self.assertIn("workflow-audit-status.md", feedback)
        self.assertIn("data-dump.json", feedback)
        # Should NOT flag package.json
        self.assertNotIn("package.json", feedback)

    def test_mobile_overflow_finding_cites_hunk(self):
        # Issue #1116: fixed-pixel widths render the Mobile UX
        # advisory but left findings empty. The finding must cite
        # the file plus the added line.
        pr = {"number": 8, "head": {"ref": "ui-branch"}, "title": "UI change"}
        diff = (
            "+++ b/src/components/Panel.tsx\n"
            "@@ -1,1 +1,1 @@\n"
            '-<div className="panel">\n'
            '+<div className="w-[480px] whitespace-nowrap">'
        )
        checks = {"check_runs": []}

        feedback = self.orchestrator.evaluate_pr_heuristics(pr, diff, checks)
        self.assertIn("Mobile UX Verification", feedback)

        findings = self.orchestrator.collect_pr_findings(pr, diff, checks)
        ov = [f for f in findings if f["rule"] == "mobile-overflow"]
        self.assertEqual(len(ov), 1)
        self.assertEqual(ov[0]["file"], "src/components/Panel.tsx")
        self.assertTrue(any("w-[480px]" in line for line in ov[0]["evidence"]))

    def test_touch_target_finding_cites_hunk(self):
        # Issue #1116: sub-48px fixed-size buttons render the touch
        # target advisory but left findings empty.
        pr = {"number": 9, "head": {"ref": "ui-branch"}, "title": "UI change"}
        diff = (
            "+++ b/src/components/Icon.tsx\n"
            "@@ -1,1 +1,1 @@\n"
            "-<span>x</span>\n"
            '+<button className="h-[24px] w-[24px]">x</button>'
        )
        checks = {"check_runs": []}

        findings = self.orchestrator.collect_pr_findings(pr, diff, checks)
        tt = [f for f in findings if f["rule"] == "touch-target"]
        self.assertEqual(len(tt), 1)
        self.assertEqual(tt[0]["file"], "src/components/Icon.tsx")
        self.assertTrue(any("h-[24px]" in line for line in tt[0]["evidence"]))

    def test_merge_conflict_finding_when_unmergeable(self):
        # Issue #1116: the merge-conflict advisory rendered with no
        # matching findings entry.
        pr = {
            "number": 10,
            "head": {"ref": "ui-branch"},
            "title": "UI change",
            "mergeable": False,
        }
        diff = "+++ b/src/App.tsx\n+<br/>"
        checks = {"check_runs": []}

        feedback = self.orchestrator.evaluate_pr_heuristics(pr, diff, checks)
        self.assertIn("Merge Conflicts", feedback)

        findings = self.orchestrator.collect_pr_findings(pr, diff, checks)
        mc = [f for f in findings if f["rule"] == "merge-conflict"]
        self.assertEqual(len(mc), 1)
        self.assertEqual(mc[0]["severity"], "error")


if __name__ == "__main__":
    unittest.main()
