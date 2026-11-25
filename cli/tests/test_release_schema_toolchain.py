"""Release schemas must use the checked-out CLI, not a global old td."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ReleaseSchemaToolchainTests(unittest.TestCase):
    """Pin the release job prerequisite without executing a publication."""

    def test_release_provisions_pinned_schema_binaries_before_use(self):
        """Both pinned binaries must exist before the schema step runs."""
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        start = workflow.index("      - name: Provision release schema toolchain")
        end = workflow.index("      - name:", start + 10)
        provision = workflow[start:end]
        self.assertLess(start, workflow.index("      - name: Sync schemas/contracts"))
        self.assertIn("python3 -m venv .venv", provision)
        self.assertIn(".venv/bin/python -m pip install -e ./cli", provision)
        self.assertIn("test -x .venv/bin/python3", provision)
        self.assertIn("test -x .venv/bin/td", provision)
        self.assertNotIn("continue-on-error", provision)
        self.assertNotIn("|| true", provision)
        self.assertIn("run: .venv/bin/python -m pytest cli/tests/", workflow)

    def test_verifier_keeps_fail_closed_venv_contract(self):
        """Repair setup rather than weakening the verifier contract."""
        verifier = (ROOT / "scripts/verify-schemas.mjs").read_text()
        self.assertIn("const pythonPath = '.venv/bin/python3'", verifier)
        self.assertIn("const tdPath = '.venv/bin/td'", verifier)
        self.assertIn("process.exit(254)", verifier)


if __name__ == "__main__":
    unittest.main()
