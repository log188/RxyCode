from __future__ import annotations

from RxyCode.RxyCode1_1_0.utils.atomic_file import atomic_write_text


def test_batch_script_is_written_with_crlf_for_cmd(tmp_path):
    target = tmp_path / "run.bat"

    atomic_write_text(target, "@echo off\nREM test\nexit /b 0\n")

    assert target.read_bytes() == b"@echo off\r\nREM test\r\nexit /b 0\r\n"


def test_non_batch_text_keeps_supplied_line_endings(tmp_path):
    target = tmp_path / "notes.txt"
    content = "first\nsecond\r\n"

    atomic_write_text(target, content)

    with open(target, encoding="utf-8", newline="") as f:
        assert f.read() == content
