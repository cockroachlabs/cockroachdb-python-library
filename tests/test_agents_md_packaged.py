"""Teeth test: the consumer AGENTS.md is baked into the base `cockroachdb` wheel.

The file is injected at wheel-build time via force-include in
packages/cockroachdb/pyproject.toml, so an editable `uv sync` install does not
expose it — we build the wheel and inspect it directly. Fails if the guide is
missing or empty (i.e. the force-include regressed).
"""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BASE_PKG = REPO_ROOT / "packages" / "cockroachdb"


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv required to build the wheel")
def test_agents_md_packaged_in_base_wheel(tmp_path: Path) -> None:
    subprocess.run(
        ["uv", "build", "-o", str(tmp_path)],
        cwd=BASE_PKG,
        check=True,
        capture_output=True,
    )
    wheels = list(tmp_path.glob("cockroachdb-*.whl"))
    assert wheels, "no base cockroachdb wheel was built"

    with zipfile.ZipFile(wheels[0]) as zf:
        assert "cockroachdb/AGENTS.md" in zf.namelist(), (
            "AGENTS.md missing from wheel — force-include regressed"
        )
        assert zf.getinfo("cockroachdb/AGENTS.md").file_size > 0, "AGENTS.md is empty"
