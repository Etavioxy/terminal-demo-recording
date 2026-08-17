#!/usr/bin/env python3
"""Python-first recorder launcher for terminal-demo-recording."""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_PORT = 9999


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch recorder with Python-owned startup")
    parser.add_argument("cast_file", nargs="?", help="Output .cast path")
    parser.add_argument("--cwd", help="Working directory for recorded commands (default: current directory)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--new-window", action="store_true", help="Windows only: relaunch in a new console window")
    parser.add_argument("--run-recorder", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--wait", action="store_true", help="Wait until the TCP server is accepting connections")
    parser.add_argument("--wait-timeout", type=float, default=20.0, help="Maximum seconds to wait for the TCP server")
    parser.add_argument("--shell", default="bash", choices=["bash", "powershell"], help="Shell environment for the recording window (Windows only)")
    parser.add_argument("--cols", type=int, default=200, help="Terminal columns for recording (default: 200)")
    parser.add_argument("--rows", type=int, default=60, help="Terminal rows for recording (default: 60)")
    return parser


def windows_creation_flags() -> int:
    return getattr(subprocess, "CREATE_NEW_CONSOLE", 0)


def python_executable() -> str:
    if os.name == "nt":
        launcher = shutil.which("py")
        if launcher:
            return launcher
    return sys.executable


def python_command() -> list[str]:
    executable = python_executable()
    if os.name == "nt" and Path(executable).name.lower() in {"py", "py.exe"}:
        return [executable, "-3"]
    return [executable]


def wait_for_server(port: int, timeout_seconds: float) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def normalize_for_windows_arg(path: Path) -> str:
    return str(path)


def relaunch_command(cast_path: Path, port: int, cwd: str | None, wait: bool, wait_timeout: float, shell: str, cols: int, rows: int) -> list[str]:
    cmd = python_command() + [
        str(Path(__file__).resolve()),
        str(cast_path),
        "--port",
        str(port),
        "--run-recorder",
    ]
    if cwd:
        cmd += ["--cwd", cwd]
    if wait:
        cmd += ["--wait", "--wait-timeout", str(wait_timeout)]
    cmd += ["--shell", shell, "--cols", str(cols), "--rows", str(rows)]
    return cmd


def running_in_real_windows_console() -> bool:
    if os.name != "nt":
        return True
    return not (os.environ.get("TERM_PROGRAM") == "vscode" or os.environ.get("WT_SESSION") or os.environ.get("MSYSTEM"))


def status_line(message: str) -> None:
    print(message, flush=True)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_cast_path() -> Path:
    return repo_root() / "recordings" / "demo.cast"


def resolve_cast_path(raw: str | None) -> Path:
    if not raw:
        return default_cast_path()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = repo_root() / path
    return path.resolve()


def server_entrypoint() -> Path:
    return Path(__file__).resolve().with_name("tcp-server.py")


def recorder_binary() -> str:
    if os.name == "nt":
        candidate = shutil.which("PowerSession") or shutil.which("PowerSession.exe")
        if not candidate:
            raise RuntimeError("PowerSession executable not found in PATH")
        return candidate

    candidate = shutil.which("asciinema")
    if not candidate:
        raise RuntimeError("asciinema executable not found in PATH")
    return candidate


def shlex_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def command_string(parts: list[str], for_shell: str = "cmd") -> str:
    """Build command string for given shell."""
    if for_shell == "bash":
        return " ".join(shlex_quote(part) for part in parts)
    return subprocess.list2cmdline(parts)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def launch_in_new_window(cast_path: Path, port: int, cwd: str | None, wait: bool, wait_timeout: float, shell: str, cols: int, rows: int) -> int:
    child_cmd = relaunch_command(cast_path, port, cwd, wait, wait_timeout, shell, cols, rows)
    if shell == "bash":
        bash_path = shutil.which("bash")
        if not bash_path:
            raise RuntimeError("bash not found in PATH")
        shell_cmd = [bash_path, "-lc", command_string(child_cmd, for_shell="bash")]
    else:
        shell_cmd = ["cmd.exe", "/c", command_string(child_cmd, for_shell="cmd")]
    subprocess.Popen(shell_cmd, creationflags=windows_creation_flags())
    status_line(f"Launched recorder in new window: {cast_path}")
    if wait:
        status_line(f"Waiting for TCP server on 127.0.0.1:{port}")
        if not wait_for_server(port, wait_timeout):
            raise RuntimeError(f"timed out waiting for TCP server on port {port}")
        status_line("TCP server is ready")
    return 0


def validate_windows_console(force_new_window: bool) -> None:
    if os.name != "nt":
        return
    if running_in_real_windows_console():
        return
    if force_new_window:
        raise RuntimeError("PowerSession must run in a real Windows console; use --new-window from shells like Git Bash or terminal integrations")


def maybe_wait_after_launch(port: int, wait: bool, wait_timeout: float) -> None:
    if not wait:
        return
    status_line(f"Waiting for TCP server on 127.0.0.1:{port}")
    if not wait_for_server(port, wait_timeout):
        raise RuntimeError(f"timed out waiting for TCP server on port {port}")
    status_line("TCP server is ready")


def remove_launcher_scripts() -> None:
    for name in ("start-recording.cmd", "start-recording.sh"):
        path = Path(__file__).resolve().parent / name
        if path.exists():
            path.unlink()


def print_usage_hint() -> None:
    status_line(f"Start recording with: {python_executable()} {Path(__file__).resolve()} --new-window --wait")
    status_line(f"Or custom cast: {python_executable()} {Path(__file__).resolve()} recordings/terminal-demo-recording/demo.cast --new-window --wait")


def ensure_python_only_entrypoints() -> None:
    remove_launcher_scripts()
    print_usage_hint()


def events_path_for(cast_path: Path) -> Path:
    """事件日志与 cast 同目录、同名派生：demo.cast -> demo.events.jsonl。

    使每次录制的可重放日志随 cast 一一对应、一起保留，不再用固定路径互相覆盖。
    """
    return cast_path.with_suffix(".events.jsonl")


def run_recorder(cast_path: Path, port: int, cwd: str | None, wait: bool, wait_timeout: float, force_new_window: bool, cols: int, rows: int) -> int:
    ensure_parent(cast_path)
    recorder = recorder_binary()
    events_path = events_path_for(cast_path)
    server_cmd = python_command() + [
        str(server_entrypoint()), "--port", str(port),
        "--cols", str(cols), "--rows", str(rows),
        "--events", str(events_path),
    ]
    if cwd:
        server_cmd += ["--cwd", cwd]

    if os.name == "nt":
        validate_windows_console(force_new_window)
        recorder_cmd = [recorder, "rec", "-f", "--stdin", "-c", command_string(server_cmd), normalize_for_windows_arg(cast_path)]
    else:
        recorder_cmd = [recorder, "rec", "-c", command_string(server_cmd), "--overwrite", str(cast_path)]

    status_line(f"Recording to: {cast_path}")
    status_line(f"Event log: {events_path}")
    if cwd:
        status_line(f"Working directory: {cwd}")
    status_line(f"Recorder command: {command_string(recorder_cmd)}")
    return subprocess.run(recorder_cmd).returncode


def preflight_dependencies() -> None:
    """录制前探测可选依赖，缺失则警告（不中止录制）。

    在 launcher 进程探测，与 server 同一个 py 解释器，故结果能代表 server 真实环境；
    输出走 recorder 日志、不进 cast。真正降级发生时 server 端还有 warn-once 兜底。
    """
    if os.name == "nt":
        try:
            import winpty  # noqa: F401
        except ImportError as e:
            status_line(f"[!] 缺少 pywinpty（ConPTY 真 TTY）→ TUI 录制会退化成 pipe、画面失真。"
                        f"修复: pip install pywinpty   [{e}]")
    try:
        import pyte  # noqa: F401
    except ImportError as e:
        status_line(f"[!] 缺少 pyte（整屏快照）→ #EXEC/#TYPE 无快照返回。"
                    f"修复: pip install pyte   [{e}]")


def run_python_owned_launch(cast_path: Path, port: int, cwd: str | None, new_window: bool, wait: bool, wait_timeout: float, shell: str, cols: int, rows: int) -> int:
    ensure_python_only_entrypoints()
    preflight_dependencies()
    if os.name == "nt" and new_window:
        return launch_in_new_window(cast_path, port, cwd, wait, wait_timeout, shell, cols, rows)
    return run_recorder(cast_path, port, cwd, wait, wait_timeout, force_new_window=True, cols=cols, rows=rows)


def architecture_summary() -> str:
    return "现在仍然是 C-S 架构：proxy/client 通过 TCP 连接 server；只是 recorder 启动入口改成了 Python 主导。"


def main() -> int:
    args = build_parser().parse_args()
    cast_path = resolve_cast_path(args.cast_file)
    cwd = args.cwd
    shell = args.shell

    if args.run_recorder:
        return run_recorder(cast_path, args.port, cwd, args.wait, args.wait_timeout, force_new_window=False, cols=args.cols, rows=args.rows)

    return run_python_owned_launch(cast_path, args.port, cwd, args.new_window, args.wait, args.wait_timeout, shell, args.cols, args.rows)


if __name__ == "__main__":
    raise SystemExit(main())
