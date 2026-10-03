"""A stale editable install must not choose scheduled paper-task source."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "ops" / "run_paper_task.py"
MODULE = "sportsbet.quant.kalshi_stat_only_next_capture"


def test_launcher_overrides_foreign_pythonpath_without_collecting(tmp_path):
    (tmp_path / "sportsbet.py").write_text("raise RuntimeError('foreign source imported')", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(LAUNCHER), "--module", MODULE, "--inspect-source"],
        cwd=tmp_path, env={**os.environ, "PYTHONPATH": str(tmp_path)},
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    proof = json.loads(result.stdout)
    expected = ROOT / "src" / "sportsbet" / "quant" / "kalshi_stat_only_next_capture.py"
    assert Path(proof["source"]) == expected
    assert proof["source_sha256"] == hashlib.sha256(expected.read_bytes()).hexdigest()


def test_launcher_rejects_other_modules_before_execution(tmp_path):
    result = subprocess.run(
        [sys.executable, str(LAUNCHER), "--module", "sportsbet.worker"],
        cwd=tmp_path, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode != 0
    assert "invalid choice" in result.stderr
