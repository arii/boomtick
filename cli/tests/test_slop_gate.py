"""Offline regression tests for the structural slop ratchet and advisory prose scan."""
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / '.agents/scripts/audit-ai-slop.py'
spec = importlib.util.spec_from_file_location('slop_audit', SCRIPT)
slop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(slop)


@pytest.mark.parametrize('body', ['pass', 'continue', 'break', 'return', 'return None', 'return False', 'return 0', 'return ""'])
def test_new_swallowed_handler_fails_and_baselined_passes(tmp_path, body):
    (tmp_path / 'fixture.py').write_text('def work():\n    while True:\n        try:\n            risky()\n        except Exception:\n            ' + body + '\n')
    baseline = {'swallow_exceptions': {}, 'unreferenced_wrappers': []}
    assert any('swallow-exception' in item for item in slop.gate_failures(tmp_path, baseline))
    baseline['swallow_exceptions'] = {path: dict(counts) for path, counts in slop.find_swallow_exceptions(tmp_path).items()}
    assert slop.gate_failures(tmp_path, baseline) == []


def test_handled_error_not_flagged(tmp_path):
    (tmp_path / 'fixture.py').write_text('try:\n    risky()\nexcept Exception:\n    recover()\n')
    assert slop.find_swallow_exceptions(tmp_path) == {}


def test_prose_case_insensitive_advisory(tmp_path):
    (tmp_path / 'config.yaml').write_text('categories:\n  jargon:\n    terms: [synergy]\n')
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src/page.md').write_text('SYNERGY')
    auditor = slop.AISlopAuditor(str(tmp_path), 'config.yaml')
    auditor.run()
    assert len(auditor.violations) == 1
    assert auditor.violations[0]['term'] == 'synergy'
    assert slop.gate_failures(tmp_path, {'swallow_exceptions': {}, 'unreferenced_wrappers': []}) == []


def test_config_error_exits_nonzero(tmp_path):
    script = tmp_path / '.agents/scripts/audit-ai-slop.py'
    script.parent.mkdir(parents=True)
    script.write_text(SCRIPT.read_text())
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert 'Slop scanner error' in result.stderr


def test_bad_python_is_scanner_error(tmp_path):
    (tmp_path / 'bad.py').write_text('def broken(')
    with pytest.raises(RuntimeError, match='Cannot scan Python file'):
        slop.find_swallow_exceptions(tmp_path)


def test_prose_scanner_failure_not_no_matches(tmp_path, monkeypatch):
    (tmp_path / 'config.yaml').write_text('categories:\n  jargon:\n    terms: [synergy]\n')
    (tmp_path / 'src').mkdir()
    monkeypatch.setattr(slop.subprocess, 'run', lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 2, '', 'fixture scanner failure'))
    with pytest.raises(RuntimeError, match='Prose scanner failed'):
        slop.AISlopAuditor(str(tmp_path), 'config.yaml').run()
