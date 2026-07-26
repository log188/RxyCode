"""RxyCode CLI and Ink frontend launcher."""

import sys
import os

# CRITICAL: Set UTF-8 console encoding BEFORE any other imports/output
if sys.platform == "win32":
    try:
        os.system("chcp 65001 >nul 2>&1")
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleCP(65001)
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass

import click

from . import __version__


def _find_available_port(start_port: int = 8765, max_tries: int = 16) -> int:
    """Find an available port starting from start_port.

    The embedded API is loopback-only, so probe the exact address it uses.
    """
    import socket
    for offset in range(max_tries):
        port = start_port + offset
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"No available port found in range {start_port}-{start_port + max_tries - 1}")


def _wait_for_api_ready(port: int, token: str, timeout: float = 30.0) -> bool:
    import urllib.request
    import time as _time

    deadline = _time.time() + timeout
    url = f"http://127.0.0.1:{port}/status"
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
    )
    while _time.time() < deadline:
        try:
            with urllib.request.urlopen(request, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        _time.sleep(0.5)
    return False


def _launch_ink_tui(model, port):
    """Launch the TypeScript + Ink TUI."""
    import subprocess
    import threading
    import time
    import os
    from .log.logger import get_logger
    _log = get_logger()

    frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")

    package_json = os.path.join(frontend_dir, "package.json")
    dist_entry = os.path.join(frontend_dir, "dist", "index.js")
    if not os.path.exists(package_json) or not os.path.exists(dist_entry):
        raise click.ClickException(
            "Ink frontend runtime is missing. Reinstall RxyCode or run "
            "'npm run build' in the frontend directory."
        )

    import shutil
    node_exe = shutil.which("node")
    if not node_exe:
        raise click.ClickException(
            "Node.js 20 or newer is required by the Ink frontend but was not "
            "found on PATH."
        )

    # Find an available port (allows multiple windows)
    port = _find_available_port(port)
    # One high-entropy bearer credential per embedded API launch. It is passed
    # only through process memory/environment and is never placed in a URL or
    # log record.
    import secrets
    api_token = secrets.token_urlsafe(32)

    # Start API server in background thread
    api_error: list[str] = []

    def run_api():
        # 不使用 logging.disable(logging.INFO) — 它会全局禁用所有 INFO 级别日志，
        # 包括我们的 "rxycode" logger。改为只抑制 uvicorn 的日志。
        import logging
        logging.getLogger("uvicorn").setLevel(logging.WARNING)
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        try:
            from .api_server import run_api_server
            run_api_server(port=port, token=api_token)
        except Exception as e:
            api_error.append(str(e))

    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()
    _log.info("API server thread started", extra={"port": port})

    # Wait for API server to become ready (replaces fixed 3s sleep)
    api_start = time.time()
    api_ready = _wait_for_api_ready(port, token=api_token, timeout=30.0)

    if not api_ready:
        _log.error("API server timeout", extra={"port": port, "timeout_sec": 30})
        reason = f" Reason: {api_error[0]}" if api_error else ""
        raise click.ClickException(
            f"API server failed to start on port {port} within 30s.{reason}"
        )

    print(f"RxyCode API ready at http://127.0.0.1:{port}")
    _log.info("API server ready", extra={"port": port, "elapsed_sec": f"{time.time() - api_start:.1f}"})

    # Launch Ink TUI using Popen for proper signal handling
    env = os.environ.copy()
    env["RXYCODE_API_PORT"] = str(port)
    # Point the TUI at the exact IPv4 loopback URL the API binds to, so a
    # "localhost" -> IPv6 ::1 resolution on the user's machine can't cause
    # ECONNREFUSED ("error connect").
    env["RXYCODE_API_URL"] = f"http://127.0.0.1:{port}"
    env["RXYCODE_API_TOKEN"] = api_token

    _log.info("Launching Ink TUI", extra={"frontend_dir": frontend_dir, "port": port, "node": node_exe})

    proc = None
    try:
        proc = subprocess.Popen(
            [node_exe, dist_entry],
            cwd=frontend_dir,
            env=env,
            shell=False,
        )
        _log.info("Ink TUI started", extra={"pid": proc.pid, "node": node_exe, "entry": dist_entry})
        returncode = proc.wait()
        _log.info("Ink TUI exited", extra={"returncode": returncode})
        if returncode != 0:
            raise click.ClickException(
                f"Ink frontend exited with status {returncode}."
            )
    except KeyboardInterrupt:
        if proc:
            proc.terminate()
            proc.wait(timeout=5)
        _log.warn("User interrupted (Ctrl-C)")
    except click.ClickException:
        raise
    except Exception as e:
        _log.error(f"Ink TUI launch failed: {e}", exc_info=True)
        raise click.ClickException(f"Ink frontend failed to launch: {e}") from e
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            _log.info("Ink TUI terminated in finally")


def _resolve_model_label(model):
    """#3: Resolve the startup model label from config instead of the literal
    'default'. When the CLI --model is given we use it verbatim; otherwise we
    read the active model's model_name from the config so the startup log shows
    the real model (e.g. deepseek-v4-flash) rather than a misleading 'default'.
    """
    if model:
        return model
    try:
        from .config.settings import load_config
        cfg = load_config()
        active = cfg.get("active_model", "")
        models = cfg.get("models", {})
        if active and active in models:
            return models[active].get("model_name", active)
        for m in models.values():
            return m.get("model_name", active or "default")
    except Exception:
        pass
    return "default"


@click.group(invoke_without_command=True)
@click.pass_context
@click.option("--model", "-m", default=None, help="Model name to use")
@click.option("--api", is_flag=True, default=False, help="Start API server only")
@click.option("--api-port", default=8765, help="API server port")
@click.option("--log-level", default="INFO", help="日志级别: DEBUG/INFO/WARN/ERROR")
@click.option("--print-logs", is_flag=True, default=False, help="同时将日志输出到 stderr")
@click.version_option(version=__version__, prog_name="RxyCode")
def cli(ctx, model, api, api_port, log_level, print_logs):
    """RxyCode - General-Purpose AI Agent"""
    if ctx.invoked_subcommand is None:
        # 初始化应用级日志（对标 opencode 日志模式，key=value 结构化格式）
        from .log.logger import setup_logging
        _log = setup_logging(level=log_level, print_logs=print_logs)

        if api:
            _log.info("RxyCode started", extra={"mode": "api", "port": api_port})
            from .api_server import run_api_server
            import secrets
            api_token = secrets.token_urlsafe(32)
            # Standalone API clients need an explicit one-time handoff. Keep
            # the credential on the controlling terminal, never in the logger
            # or command-line arguments/process list.
            click.echo(f"RxyCode API bearer token: {api_token}", err=True)
            run_api_server(port=api_port, token=api_token)
        else:
            # Default: launch Ink TUI
            _log.info("RxyCode started", extra={"mode": "ink", "model": _resolve_model_label(model), "port": api_port})
            _launch_ink_tui(model, api_port)

        _log.info("RxyCode exited")
        # 确保日志写入磁盘（进程退出前 flush 所有 handlers）
        for h in _log.handlers:
            try:
                h.flush()
            except Exception:
                pass


@cli.command()
@click.argument("subcommand", default="list")
@click.argument("name", default="")
def config(subcommand, name):
    """Manage model configuration."""
    from .config import model_manager
    from .config.settings import load_config

    if subcommand == "list":
        cfg = load_config()
        models = cfg.get("models", {})
        active = cfg.get("active_model", "")
        for name, mcfg in models.items():
            status = " (active)" if name == active else ""
            print(f"{name}{status} - {mcfg.get('model_name', '')} @ {mcfg.get('base_url', '')}")
    elif subcommand == "test-model":
        if not name:
            print("Usage: RxyCode config test-model <name>")
            return
        result = model_manager.test_model_connection(name)
        if result["success"]:
            print(f"Connected ({result['elapsed']}s)")
        else:
            print(f"Failed: {result['error']}")
    elif subcommand == "set-active":
        if not name:
            print("Usage: RxyCode config set-active <name>")
            return
        if model_manager.set_active_model(name):
            print(f"Active model: {name}")
        else:
            print(f"Model '{name}' not found")
    elif subcommand == "remove":
        if not name:
            print("Usage: RxyCode config remove <name>")
            return
        if model_manager.remove_model(name):
            print(f"Removed: {name}")
        else:
            print(f"Model '{name}' not found")
    else:
        print("Subcommands: list, test-model, set-active, remove")


if __name__ == "__main__":
    cli()
