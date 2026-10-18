"""A scanned repository must not replace the analyzer module on sys.path."""

import subprocess

import pytest

from codegate.engines.analyzers.bandit_analyzer import BanditAnalyzer
from codegate.engines.analyzers.radon_analyzer import RadonAnalyzer
from codegate.engines.analyzers.ruff_analyzer import RuffAnalyzer


@pytest.mark.parametrize("analyzer", [RuffAnalyzer(), BanditAnalyzer(), RadonAnalyzer()])
def test_repo_cannot_shadow_installed_analyzer(analyzer, tmp_path):
    marker = tmp_path / "shadow-module-executed.txt"
    module = analyzer.name.value.lower()
    (tmp_path / f"{module}.py").write_text(
        "from pathlib import Path\n"
        "Path('shadow-module-executed.txt').write_text('executed')\n"
        "print('{}')\n", encoding="utf-8"
    )
    process = subprocess.run(analyzer.command, cwd=tmp_path, capture_output=True, timeout=30)
    assert not marker.exists(), f"Untrusted {module}.py was executed as the analyzer"
    result = analyzer.parse_output(process.stdout.decode("utf-8"), process.stderr.decode("utf-8"), process.returncode)
    assert result.error_message is None
