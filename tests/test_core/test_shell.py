"""
Tests for utils/shell.py - Shell command execution and translation.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestShellExecutor:
    def _make_executor(self):
        from RxyCode.RxyCode1_1_0.utils.shell import ShellExecutor
        return ShellExecutor()

    def test_init(self):
        executor = self._make_executor()
        assert executor is not None

    def test_detect_shell(self):
        executor = self._make_executor()
        shell = executor._detect_shell()
        assert shell is not None

    def test_has_powershell(self):
        executor = self._make_executor()
        result = executor._has_powershell()
        assert isinstance(result, bool)

    def test_detect_desktop(self):
        executor = self._make_executor()
        executor._detect_desktop()  # should not crash

    def test_is_powershell_syntax(self):
        executor = self._make_executor()
        result = executor._is_powershell_syntax("Get-ChildItem")
        assert isinstance(result, bool)

    def test_translate_command(self):
        executor = self._make_executor()
        result = executor.translate_command("ls")
        assert result is not None

    def test_powershell_translates_cmd_chain_and_start(self):
        executor = self._make_executor()
        executor.shell_type = "powershell"
        cmd, shell = executor.translate_command(
            r"cd /d D:\agent-demo\RxyCode\RxyCode1_1_0 && dir"
        )
        assert shell == "powershell"
        assert "&&" not in cmd
        assert "Set-Location" in cmd
        assert ";" in cmd

        started, shell2 = executor.translate_command("start cmd /k python hello_rxy.py")
        assert shell2 == "powershell"
        assert "Start-Process" in started
        assert "cmd.exe" in started
        assert "python hello_rxy.py" in started

    def test_powershell_translates_posix_ls_flags(self):
        executor = self._make_executor()
        executor.shell_type = "powershell"
        cmd, shell = executor.translate_command("ls -la")
        assert shell == "powershell"
        assert "Get-ChildItem -Force" in cmd

        cmd2, _ = executor.translate_command("pwd && ls -l")
        assert "Get-ChildItem" in cmd2
        assert "ls -l" not in cmd2

    def test_powershell_translates_posix_grep(self):
        """POSIX grep → Select-String（B7：模型高频输出 grep 语法）。"""
        executor = self._make_executor()
        executor.shell_type = "powershell"
        cmd, shell = executor.translate_command('grep -n "add_node" core/graph.py')
        assert shell == "powershell"
        assert "Select-String" in cmd
        assert "grep" not in cmd
        assert "core/graph.py" in cmd

    def test_powershell_translates_posix_cat(self):
        """POSIX cat → Get-Content（B7）。"""
        executor = self._make_executor()
        executor.shell_type = "powershell"
        cmd, shell = executor.translate_command("cat counter.py")
        assert shell == "powershell"
        assert "Get-Content" in cmd
        assert "cat " not in cmd

    def test_powershell_translates_dev_null_redirect(self):
        """POSIX 2>/dev/null → 2>$null（B7，现有只覆盖 2>nul）。"""
        executor = self._make_executor()
        executor.shell_type = "powershell"
        cmd, shell = executor.translate_command("ls test.py 2>/dev/null")
        assert shell == "powershell"
        assert "2>/dev/null" not in cmd
        assert "2>$null" in cmd

    def test_powershell_translates_pwd(self):
        """POSIX pwd → Get-Location（B7）。"""
        executor = self._make_executor()
        executor.shell_type = "powershell"
        cmd, shell = executor.translate_command("pwd")
        assert shell == "powershell"
        assert "Get-Location" in cmd

    def test_powershell_translates_or_fallback(self):
        """POSIX || → 失败分支（B7：cmd1 || cmd2 语义）。"""
        executor = self._make_executor()
        executor.shell_type = "powershell"
        cmd, shell = executor.translate_command("cat x.py || echo missing")
        assert shell == "powershell"
        assert "||" not in cmd
        assert "echo missing" in cmd

    def test_powershell_translates_posix_find(self):
        """POSIX find -name → Get-ChildItem -Recurse -Filter（B7）。"""
        executor = self._make_executor()
        executor.shell_type = "powershell"
        cmd, shell = executor.translate_command('find . -name "graph.py"')
        assert shell == "powershell"
        assert "Get-ChildItem" in cmd
        assert "-Recurse" in cmd
        assert "graph.py" in cmd

    def test_powershell_translates_grep_rl(self):
        """POSIX grep -rl → Select-String 递归（B7）。"""
        executor = self._make_executor()
        executor.shell_type = "powershell"
        cmd, shell = executor.translate_command('grep -rl "goal_planner" core/')
        assert shell == "powershell"
        assert "Select-String" in cmd
        assert "-Recurse" in cmd
        assert "goal_planner" in cmd

    def test_powershell_translate_does_not_touch_quoted_text(self):
        """引号内的普通文本（echo 输出等）不被转换误改（luna R1）。"""
        executor = self._make_executor()
        executor.shell_type = "powershell"
        cmd, shell = executor.translate_command('echo "pwd && cat readme"')
        assert shell == "powershell"
        # 引号内的 pwd/cat 不应被转换为 Get-Location/Get-Content
        assert "Get-Location" not in cmd
        assert "Get-Content" not in cmd

    def test_powershell_translate_quoted_redirect_and_or(self):
        """引号内的 2>/dev/null 与 || 不被转换（luna R2）。"""
        executor = self._make_executor()
        executor.shell_type = "powershell"
        cmd, _ = executor.translate_command('echo "2>/dev/null"')
        assert '"2>/dev/null"' in cmd

        cmd2, _ = executor.translate_command('echo "a || b"')
        assert '"a || b"' in cmd2
        assert "if (-not" not in cmd2

        cmd3, _ = executor.translate_command('echo "x; pwd"')
        assert '"x; pwd"' in cmd3
        assert "Get-Location" not in cmd3

    def test_powershell_translate_unclosed_quote_protected(self):
        """未闭合引号后的文本不受转换（luna R3-1）。"""
        executor = self._make_executor()
        executor.shell_type = "powershell"
        cmd, _ = executor.translate_command('echo "2>/dev/null')
        assert '"2>/dev/null' in cmd
        assert "2>$null" not in cmd

    def test_powershell_translate_escaped_quote_protected(self):
        """转义引号不结束保护范围（luna R3-2）。"""
        executor = self._make_executor()
        executor.shell_type = "powershell"
        cmd, _ = executor.translate_command(r'echo "a \" 2>/dev/null"')
        assert "2>/dev/null" in cmd
        assert "2>$null" not in cmd

    def test_powershell_translate_grep_multiple_files(self):
        """grep 多文件参数不丢失（luna R3-4）。"""
        executor = self._make_executor()
        executor.shell_type = "powershell"
        cmd, _ = executor.translate_command('grep -n "pat" file1 file2')
        assert "file1" in cmd
        assert "file2" in cmd

    def test_powershell_translate_or_then_pwd(self):
        """|| 分支内的 pwd 也转换（luna R3-5）。"""
        executor = self._make_executor()
        executor.shell_type = "powershell"
        cmd, _ = executor.translate_command("echo x || pwd")
        assert "if (-not $?)" in cmd
        assert "Get-Location" in cmd

    def test_powershell_translate_grep_after_cd_chain(self):
        """cd && grep 链中 grep 也转换（B8：; 后位置）。"""
        executor = self._make_executor()
        executor.shell_type = "powershell"
        cmd, _ = executor.translate_command(
            r'cd "D:\x" && grep -n "class UsageTrackingLLM" core/agent_v2.py'
        )
        assert "Select-String" in cmd
        assert "grep" not in cmd

    def test_powershell_translate_grep_after_semicolon(self):
        """echo x; grep 链中 grep 也转换（B8）。"""
        executor = self._make_executor()
        executor.shell_type = "powershell"
        cmd, _ = executor.translate_command('echo hi; grep -n "x" f.py')
        assert "Select-String" in cmd

    def test_powershell_translate_grep_pattern_safe_quoting(self):
        """grep pattern 用 PS 单引号包裹，$ 不展开、引号/反引号保留（luna R4-1）。"""
        executor = self._make_executor()
        executor.shell_type = "powershell"
        cmd, _ = executor.translate_command("grep '$HOME' file")
        assert "Select-String -Pattern '$HOME'" in cmd

        cmd2, _ = executor.translate_command("grep 'a\"b' file")
        assert "'a\"b'" in cmd2

        cmd3, _ = executor.translate_command("grep 'a`nb' file")
        assert "'a`nb'" in cmd3

    def test_powershell_translates_ampersand_separators(self):
        executor = self._make_executor()
        executor.shell_type = "powershell"
        cmd, shell = executor.translate_command(
            "python a.py X & echo --- & python a.py Y"
        )
        assert shell == "powershell"
        assert cmd == "python a.py X; echo ---; python a.py Y"

        # Call-operator `& 'path'` must be preserved.
        call_op, _ = executor.translate_command("& 'C:\\Program Files\\app.exe' --help")
        assert call_op.startswith("& '")
        assert "; " not in call_op

    def test_powershell_translates_cmd_dir_and_redirects(self):
        executor = self._make_executor()
        executor.shell_type = "powershell"

        bare, _ = executor.translate_command('dir /b "C:\\Users\\Administrator\\.rxycode\\skills"')
        assert bare == 'Get-ChildItem -Name "C:\\Users\\Administrator\\.rxycode\\skills"'

        bare_short, _ = executor.translate_command("dir /b")
        assert bare_short == "Get-ChildItem -Name"

        flag_after, _ = executor.translate_command('dir "C:\\tools" /b')
        assert flag_after == 'Get-ChildItem -Name "C:\\tools"'

        nul, _ = executor.translate_command("python run.py 2>nul")
        assert nul == "python run.py 2>$null"

    def test_powershell_translates_head_tail_pipes(self):
        executor = self._make_executor()
        executor.shell_type = "powershell"

        head_n, _ = executor.translate_command("curl -s https://x.test | head -50")
        assert head_n == "curl -s https://x.test | Select-Object -First 50"

        head_short, _ = executor.translate_command("python -c \"print(1)\" | head -3")
        assert head_short == "python -c \"print(1)\" | Select-Object -First 3"

        tail_n, _ = executor.translate_command("Get-Content out.txt | tail -n 4")
        assert tail_n == "Get-Content out.txt | Select-Object -Last 4"

    def test_powershell_heredoc_translates_head_with_cmd_chain(self):
        executor = self._make_executor()
        executor.shell_type = "powershell"
        heredoc = (
            "cd /d D:\\repo && python - <<'PY'\n"
            "import os\n"
            "print('ok')\n"
            "PY"
        )
        cmd, shell = executor.translate_command(heredoc)
        assert shell == "powershell"
        assert "Set-Location" in cmd
        assert "python -c" in cmd
        assert "@'" in cmd
        assert "&&" not in cmd

    def test_powershell_translates_posix_heredoc(self):
        executor = self._make_executor()
        executor.shell_type = "powershell"
        heredoc = (
            "python - <<'PY'\n"
            "import os\n"
            "print('hello', os.name)\n"
            "PY"
        )
        cmd, shell = executor.translate_command(heredoc)
        assert shell == "powershell"
        assert "python -c" in cmd
        assert "@'" in cmd
        assert "import os" in cmd
        assert "<<" not in cmd
        assert "'PY'" not in cmd

        # A plain command without heredoc must not be altered.
        plain, shell2 = executor.translate_command("python --version")
        assert shell2 == "powershell"
        assert "python --version" in plain

    def test_translate_complex_command(self):
        executor = self._make_executor()
        result = executor.translate_command("pip install flask")
        assert result is not None

    def test_execute_simple(self):
        executor = self._make_executor()
        result = executor.execute("echo hello")
        assert isinstance(result, dict)
        assert "stdout" in result or "success" in result

    def test_execute_python_command(self):
        executor = self._make_executor()
        result = executor.execute("python --version")
        assert isinstance(result, dict)

    def test_execute_invalid_command(self):
        executor = self._make_executor()
        result = executor.execute("nonexistent_command_xyz_123")
        assert isinstance(result, dict)

    def test_execute_empty_command(self):
        executor = self._make_executor()
        result = executor.execute("")
        assert isinstance(result, dict)
