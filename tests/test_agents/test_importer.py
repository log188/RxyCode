"""F18 importer + team_install two-step ask."""

from __future__ import annotations

import zipfile
from pathlib import Path

from RxyCode.RxyCode1_1_0.core.agents.importer import TeamImporter, write_sample_package
from RxyCode.RxyCode1_1_0.core.agents.registry import TeamRegistry
from RxyCode.RxyCode1_1_0.tools.team_install_tool import team_install


def test_import_directory_zip_github_and_export(tmp_path: Path) -> None:
    root = tmp_path / "teams"
    registry = TeamRegistry(root=root)
    importer = TeamImporter(registry)
    src = write_sample_package(tmp_path / "pkg", name="pkg")
    (src / "hooks").mkdir()
    (src / "hooks" / "x.py").write_text("print(1)\n", encoding="utf-8")
    name = importer.import_directory(src, group="other", local=False)
    assert name == "pkg"
    assert (root / "pkg" / "hooks.disabled").exists()

    archive = tmp_path / "pkg.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(src / "team.yaml", arcname="team.yaml")
    importer.import_zip(archive, group="other")

    def downloader(url: str, dest: Path) -> None:
        write_sample_package(dest, name="fromgh")

    importer.import_github("https://example.com/t.zip", downloader=downloader)
    exported = importer.export_directory("pkg", tmp_path / "out")
    assert (exported / "team.yaml").exists()


def test_team_install_two_questions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("RXYCODE_DATA_DIR", str(tmp_path))
    first = team_install("demo-team")
    assert "ASK_CONFIRM" in first
    second = team_install("demo-team", confirm=True, group="other")
    assert "installed" in second
