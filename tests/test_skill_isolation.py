from pathlib import Path


def test_skill_manager_uses_explicit_test_root(monkeypatch, tmp_path: Path):
    from RxyCode.RxyCode1_1_0.tools import skill_manager

    isolated = tmp_path / "skills"
    monkeypatch.setenv("RXYCODE_SKILLS_DIR", str(isolated))
    assert skill_manager.get_skills_dir() == isolated


def test_skill_tool_search_uses_only_explicit_roots(monkeypatch, tmp_path: Path):
    from RxyCode.RxyCode1_1_0.tools import skill_tool

    first = tmp_path / "one"
    second = tmp_path / "two"
    monkeypatch.setenv("RXYCODE_SKILLS_DIRS", f"{first}{__import__('os').pathsep}{second}")
    assert skill_tool._skill_dirs() == [first, second]
