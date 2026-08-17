#!/usr/bin/env python3
"""TCP server for terminal-demo-director (Linux/macOS).
Runs inside an asciinema-recorded session, accepts commands via TCP.
"""
import argparse
import base64
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import re

try:
    import pyte
    _PYTE_AVAILABLE = True
except ImportError:
    _PYTE_AVAILABLE = False

from server.pty_backend import PtyBackend, create_backend
from server import change_metrics
from server.event_log import EventLog

PORT = 9999
SHELL_PROC = None
SHELL_LOCK = threading.Lock()
SHELL_STDOUT_BUF = bytearray()
SHELL_DONE = threading.Event()
INTERACTIVE_LOCK = False
CWD = os.getcwd()
ENV = dict(os.environ)

PTY_BACKEND: PtyBackend | None = create_backend()
PTY_PROC: PtyBackend | None = None

SCREEN_COLS = 200
SCREEN_ROWS = 60
PYTE_SCREEN = None
PYTE_STREAM = None

# 变化采样：relay 每次 feed 后记 (t, 脏行数)，#VIEW 据此算稳定指数。裁掉超过最长窗的老样本。
DIRTY_LOG = []
MAX_WINDOW_S = max(change_metrics.DEFAULT_WINDOWS)

# 会话事件日志：记录每条进来的命令(seq/ts/rel_ms/wire)，供重放复现会话。main_compat 中打开。
EVENT_LOG = None

DEFAULT_EXEC_TIMEOUT_MS = 30000
DEFAULT_TYPE_TIMEOUT_MS = 3000

GRAY = "\033[90m"
GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"

# 降级 warn-once 标志：依赖缺失导致退化时各警告一次，绝不静默、也不刷屏
_WARNED_NO_PTY = False
_WARNED_NO_PYTE = False
DEBUG_LOG_PATH = Path(__file__).resolve().parents[2] / ".claude-testing" / "server-stream.log"


def _log_stream(name, chunk):
    DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DEBUG_LOG_PATH.open("ab") as handle:
        handle.write(f"[{name}] ".encode("utf-8"))
        handle.write(chunk)
        handle.write(b"\n")


def send_response(conn, text):
    lines = text.rstrip("\n") + "\n##END##\n"
    conn.sendall(lines.encode("utf-8"))


# --------------- timeout parsing ---------------

_TIMEOUT_RE = re.compile(r"\s+timeout=(\d+)\s*$")


def _parse_timeout(payload, default_ms):
    """Extract optional `timeout=<ms>` from end of payload. Returns (clean_payload, seconds)."""
    m = _TIMEOUT_RE.search(payload)
    if m:
        return payload[: m.start()], int(m.group(1)) / 1000.0
    return payload, default_ms / 1000.0


# --------------- nvim token parser ---------------
# Vim/neovim key notation reference: https://vimhelp.org/intro.txt.html
# Key codes with decimal values from Vim documentation:
# <Nul> = 0, <BS> = 8, <Tab> = 9, <NL> = 10, <CR> = 13, <Esc> = 27, <Space> = 32, <Del> = 127
# Modifier combinations: <C-x> (Control), <S-x> (Shift), <A-x>/<M-x> (Alt/Meta), <D-x> (Command/Super)

# Match vim token names: letter/digit followed by letters/digits/hyphens
# Avoids matching comparison operators like <= >= which contain < and >
_TOKEN_RE = re.compile(r"<([A-Za-z][A-Za-z0-9-]*)>")

_TOKEN_MAP = {
    # Enter/Return = \r (CR=13，见上 vimhelp 注释)；raw 模式 TUI 只认 \r，不是 \n
    "CR": "\r", "ENTER": "\r", "RETURN": "\r", "KENTER": "\r",
    "LF": "\n", "NL": "\n",   # 显式 linefeed / Ctrl-J
    # Escape
    "ESC": "\x1b", "ESCAPE": "\x1b",
    # Tab and backspace
    "TAB": "\t", "BS": "\x08", "BACKSPACE": "\x08",
    # Space and literal <
    "SPACE": " ", "LT": "<",
    # Special keys
    "NUL": "\x00", "DEL": "\x7f", "DELETE": "\x7f",
    # Navigation keys (ANSI escape sequences)
    "UP": "\x1b[A", "DOWN": "\x1b[B",
    "LEFT": "\x1b[D", "RIGHT": "\x1b[C",
    "HOME": "\x1b[H", "END": "\x1b[F",
    # Page navigation
    "PAGEUP": "\x1b[5~", "PAGEDOWN": "\x1b[6~",
    # Insert/Delete (ANSI sequences for terminal)
    "INSERT": "\x1b[2~", "KDEL": "\x1b[3~",
    # Function keys F1-F12
    "F1": "\x1bOP", "F2": "\x1bOQ", "F3": "\x1bOR", "F4": "\x1bOS",
    "F5": "\x1b[15~", "F6": "\x1b[17~", "F7": "\x1b[18~", "F8": "\x1b[19~",
    "F9": "\x1b[20~", "F10": "\x1b[21~", "F11": "\x1b[23~", "F12": "\x1b[24~",
    # Keypad keys
    "KPLUS": "+", "KMINUS": "-", "KMULTIPLY": "*", "KDIVIDE": "/",
    "KPOINT": ".", "K0": "0", "K1": "1", "K2": "2", "K3": "3", "K4": "4",
    "K5": "5", "K6": "6", "K7": "7", "K8": "8", "K9": "9",
    # Keypad navigation equivalents
    "KHOME": "\x1b[H", "KEND": "\x1b[F", "KPAGEUP": "\x1b[5~", "KPAGEDOWN": "\x1b[6~",
}


def _resolve_token(name):
    """Resolve a single <TOKEN> name to bytes. Case-insensitive.

    Supports Vim/neovim key notation from vimhelp.org/intro.txt.html:
    - <C-x> Control key combinations (Ctrl+a = ASCII 1)
    - <S-x> Shift key (returns the uppercase char)
    - <A-x> or <M-x> Alt/Meta key (ESC prefix + char)
    - <D-x> Command/Super key (ESC prefix + char, same as Alt for terminal)
    """
    upper = name.upper()
    if upper in _TOKEN_MAP:
        return _TOKEN_MAP[upper]
    # <C-a> through <C-z> - Control key combinations
    if upper.startswith("C-") and len(upper) == 3:
        ch = upper[2]
        if "A" <= ch <= "Z":
            return chr(ord(ch) - ord("A") + 1)
    # <S-x> - Shift key (uppercase the character)
    if upper.startswith("S-") and len(upper) == 3:
        ch = upper[2]
        return ch.upper() if ch.isalpha() else ch
    # <A-x> or <M-x> - Alt/Meta key (ESC prefix + char)
    if (upper.startswith("A-") or upper.startswith("M-")) and len(upper) == 3:
        ch = upper[2]
        return "\x1b" + ch.lower()
    # <D-x> - Command/Super key (same as Alt for terminal)
    if upper.startswith("D-") and len(upper) == 3:
        ch = upper[2]
        return "\x1b" + ch.lower()
    return None


def parse_nvim_tokens(text):
    """Parse nvim-style token string into raw bytes for stdin injection."""
    result = []
    pos = 0
    for m in _TOKEN_RE.finditer(text):
        if m.start() > pos:
            result.append(text[pos : m.start()])
        resolved = _resolve_token(m.group(1))
        if resolved is not None:
            result.append(resolved)
        else:
            result.append(m.group(0))  # keep unrecognized tokens as-is
        pos = m.end()
    if pos < len(text):
        result.append(text[pos:])
    return "".join(result)


def _find_powershell():
    """Locate powershell.exe, preferring full path for git-bash compatibility."""
    candidates = [
        os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                     "System32", "WindowsPowerShell", "v1.0", "powershell.exe"),
        "powershell.exe",
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return "powershell.exe"


def _shell_start_command():
    if os.name == "nt":
        return [
            _find_powershell(),
            "-NoLogo",
            "-NoProfile",
            "-Command",
            (
                "$global:ProgressPreference='SilentlyContinue'; "
                "function prompt { '' }; "
                "while ($true) { "
                "  $line = [Console]::In.ReadLine(); "
                "  if ($null -eq $line) { break }; "
                "  Invoke-Expression $line 2>&1; "
                "  [Console]::Error.WriteLine('__EXECDONE__') "
                "}"
            ),
        ]
    return ["/bin/sh"]


def _stdout_relay(proc):
    """Read from shell stdout pipe, relay to terminal, buffer for capture."""
    fd = proc.stdout.fileno()
    try:
        while True:
            chunk = os.read(fd, 8192)
            if not chunk:
                break
            _log_stream("stdout", chunk)
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
            with SHELL_LOCK:
                SHELL_STDOUT_BUF.extend(chunk)
                if PYTE_STREAM is not None:
                    try:
                        PYTE_STREAM.feed(chunk.decode("utf-8", errors="replace"))
                    except Exception:
                        pass  # pyte may not handle all escape sequences
    except (ValueError, OSError):
        pass


def _record_dirty():
    """采样一次（须持 SHELL_LOCK）：记录自上次采样以来的脏行数、清 dirty、裁老样本。

    由定时采样线程按固定间隔调用——采样与 PTY chunk 分块无关，使实验与生产同源。
    """
    if PYTE_SCREEN is None:
        return
    now = time.time()
    DIRTY_LOG.append((now, len(PYTE_SCREEN.dirty)))
    PYTE_SCREEN.dirty.clear()
    cutoff = now - MAX_WINDOW_S
    while DIRTY_LOG and DIRTY_LOG[0][0] < cutoff:
        DIRTY_LOG.pop(0)


def _dirty_sampler():
    """常驻定时采样线程：每 SAMPLE_INTERVAL_S 采一次 pyte.dirty。

    全程几乎零开销（实测单次约 0.15us、20Hz 占用 ~0.0003% CPU）；空闲时记 0、
    窗口自然衰减。固定时间网格采样消除 chunk 分块对短窗的影响。
    """
    while True:
        time.sleep(change_metrics.SAMPLE_INTERVAL_S)
        with SHELL_LOCK:
            _record_dirty()


def _wait_and_capture(timeout_s):
    """等待 timeout 让屏幕稳定，返回当前整屏快照（pyte 缺失则退回原始缓冲）。

    #TYPE 写完输入后调用、#VIEW 直接调用——只产出 snap，发送交给调用点的 send_response。
    """
    time.sleep(timeout_s)
    with SHELL_LOCK:
        snap = _capture_snapshot()
        if snap is None:
            snap = bytes(SHELL_STDOUT_BUF).decode("utf-8", errors="replace").strip()
    return snap


def _capture_snapshot():
    """Return current full-screen text from pyte emulator (caller must hold SHELL_LOCK)."""
    global _WARNED_NO_PYTE
    if PYTE_SCREEN is None:
        if not _WARNED_NO_PYTE:
            print(f"{RED}[!] pyte 不可用，无整屏快照（#EXEC/#TYPE 返回空）。修复: pip install pyte{RESET}", flush=True)
            _WARNED_NO_PYTE = True
        return None
    lines = PYTE_SCREEN.display
    return "\n".join(line.rstrip() for line in lines).rstrip("\n")


def _stderr_watch(proc):
    """Watch stderr for completion markers and relay visible output."""
    global INTERACTIVE_LOCK
    fd = proc.stderr.fileno()
    buf = b""
    try:
        while True:
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if line.rstrip(b"\r") == b"__EXECDONE__":
                    INTERACTIVE_LOCK = False
                    SHELL_DONE.set()
                else:
                    visible = line + b"\n"
                    _log_stream("stderr", visible)
                    sys.stdout.buffer.write(visible)
                    sys.stdout.buffer.flush()
                    with SHELL_LOCK:
                        SHELL_STDOUT_BUF.extend(visible)
                        if PYTE_STREAM is not None:
                            try:
                                PYTE_STREAM.feed(visible.decode("utf-8", errors="replace"))
                            except Exception:
                                pass
    except (ValueError, OSError):
        pass

    if buf and buf.rstrip(b"\r") != b"__EXECDONE__":
        visible = buf
        _log_stream("stderr", visible)
        sys.stdout.buffer.write(visible)
        sys.stdout.buffer.flush()
        with SHELL_LOCK:
            SHELL_STDOUT_BUF.extend(visible)
            if PYTE_STREAM is not None:
                try:
                    PYTE_STREAM.feed(visible.decode("utf-8", errors="replace"))
                except Exception:
                    pass


def _ensure_shell():
    global SHELL_PROC
    if SHELL_PROC is not None and SHELL_PROC.poll() is None:
        return SHELL_PROC
    shell_env = dict(ENV)
    shell_env["COLUMNS"] = str(SCREEN_COLS)
    shell_env["LINES"] = str(SCREEN_ROWS)
    SHELL_PROC = subprocess.Popen(
        _shell_start_command(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=CWD,
        env=shell_env,
    )
    threading.Thread(target=_stdout_relay, args=(SHELL_PROC,), daemon=True).start()
    threading.Thread(target=_stderr_watch, args=(SHELL_PROC,), daemon=True).start()
    time.sleep(0.5)
    return SHELL_PROC


def _send_shell_line(line):
    proc = _ensure_shell()
    if proc.poll() is not None or proc.stdin is None:
        raise RuntimeError("persistent shell is not running")
    proc.stdin.write((line + "\n").encode("utf-8"))
    proc.stdin.flush()


def _run_captured_command(program):
    return subprocess.run(
        program,
        shell=True,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=CWD,
        env=ENV,
    )


def _quote_for_powershell(cmd: str) -> str:
    """Quote command for PowerShell Invoke-Expression if executable path contains spaces."""
    if os.name != "nt":
        return cmd
    # Find the executable part (first token, may contain spaces if it's a path)
    # For Windows, executable is typically first token before args
    # If the command starts with a path-like string containing spaces, quote it
    tokens = cmd.split()
    if not tokens:
        return cmd

    # Check if first token looks like a path (has : or starts with / or \)
    first = tokens[0]
    is_path_like = (":" in first) or first.startswith("/") or first.startswith("\\") or first.startswith("~")

    if not is_path_like:
        return cmd

    # If path has spaces, we need to find where the executable ends
    # This is tricky - we look for tokens that together form a valid path ending in exe
    exe_end_idx = 0
    accumulated = ""
    for i, tok in enumerate(tokens):
        accumulated = accumulated + " " + tok if accumulated else tok
        exe_end_idx = i
        # Check if accumulated looks like a complete executable path
        if accumulated.endswith(".exe") or accumulated.endswith(".EXE"):
            break

    exe_path = " ".join(tokens[:exe_end_idx + 1])
    args = " ".join(tokens[exe_end_idx + 1:]) if exe_end_idx + 1 < len(tokens) else ""

    # Quote the executable path for PowerShell
    quoted_exe = f"& '{exe_path}'"
    return f"{quoted_exe} {args}" if args else quoted_exe


def _pty_relay(backend: PtyBackend):
    """Read from PTY output, relay to recording terminal, buffer for pyte capture."""
    try:
        while backend.isalive():
            try:
                chunk_str = backend.read(8192)
            except EOFError:
                break
            if not chunk_str:
                time.sleep(0.01)
                continue
            chunk = chunk_str.encode("utf-8", errors="replace")
            _log_stream("pty", chunk)
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
            with SHELL_LOCK:
                SHELL_STDOUT_BUF.extend(chunk)
                if PYTE_STREAM is not None:
                    try:
                        PYTE_STREAM.feed(chunk_str)
                    except Exception:
                        pass
        try:
            remaining = backend.read(8192)
            if remaining:
                chunk = remaining.encode("utf-8", errors="replace")
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
                with SHELL_LOCK:
                    SHELL_STDOUT_BUF.extend(chunk)
                    if PYTE_STREAM is not None:
                        try:
                            PYTE_STREAM.feed(remaining)
                        except Exception:
                            pass
        except (EOFError, Exception):
            pass
    except (EOFError, Exception):
        pass


def _run_exec_pty(program, conn, timeout_s):
    """Run EXEC command via PTY backend. Child processes see a real terminal."""
    global INTERACTIVE_LOCK, PTY_PROC

    if os.name == "nt":
        encoded = base64.b64encode(program.encode("utf-16le")).decode("ascii")
        ps_path = _find_powershell()
        spawn_cmd = f"{ps_path} -NoProfile -NoLogo -EncodedCommand {encoded}"
    else:
        spawn_cmd = program

    pty_env = dict(ENV)
    pty_env["COLUMNS"] = str(SCREEN_COLS)
    pty_env["LINES"] = str(SCREEN_ROWS)
    if pty_env.get("TERM", "dumb") == "dumb":
        pty_env["TERM"] = "xterm-256color"

    backend = create_backend()
    backend.spawn(spawn_cmd, cwd=CWD, rows=SCREEN_ROWS, cols=SCREEN_COLS, env=pty_env)
    PTY_PROC = backend

    relay = threading.Thread(target=_pty_relay, args=(backend,), daemon=True)
    relay.start()

    deadline = time.time() + timeout_s
    while time.time() < deadline and backend.isalive():
        time.sleep(0.05)

    time.sleep(0.15)
    with SHELL_LOCK:
        output = bytes(SHELL_STDOUT_BUF).decode("utf-8", errors="replace").strip()
        SHELL_STDOUT_BUF.clear()

    if not backend.isalive():
        INTERACTIVE_LOCK = False
        PTY_PROC = None
        send_response(conn, f"OK:{output}" if output else "OK:")
    else:
        INTERACTIVE_LOCK = True
        with SHELL_LOCK:
            snap = _capture_snapshot()
        content = snap if snap else output
        send_response(conn, f"OK:RUNNING:{content}" if content else "OK:RUNNING")


def _run_exec_piped(program, conn, timeout_s):
    """Run EXEC command via piped persistent shell (fallback / non-Windows)."""
    global INTERACTIVE_LOCK
    SHELL_DONE.clear()
    with SHELL_LOCK:
        SHELL_STDOUT_BUF.clear()
    _send_shell_line(_quote_for_powershell(program))
    if os.name != "nt":
        _send_shell_line("echo __EXECDONE__ >&2")
    finished = SHELL_DONE.wait(timeout=timeout_s)
    time.sleep(0.1)
    with SHELL_LOCK:
        output = bytes(SHELL_STDOUT_BUF).decode("utf-8", errors="replace").strip()
        SHELL_STDOUT_BUF.clear()
    if finished:
        INTERACTIVE_LOCK = False
        send_response(conn, f"OK:{output}" if output else "OK:")
    else:
        INTERACTIVE_LOCK = True
        with SHELL_LOCK:
            snap = _capture_snapshot()
        content = snap if snap else output
        send_response(conn, f"OK:RUNNING:{content}" if content else "OK:RUNNING")


def _run_exec_command(program, conn, timeout_s=None):
    global INTERACTIVE_LOCK, _WARNED_NO_PTY
    if timeout_s is None:
        timeout_s = DEFAULT_EXEC_TIMEOUT_MS / 1000.0
    print(f"{GREEN}$ {program}{RESET}", flush=True)

    if PTY_BACKEND is not None:
        _run_exec_pty(program, conn, timeout_s)
    else:
        if not _WARNED_NO_PTY:
            print(f"{RED}[!] PTY(ConPTY) 不可用，回退 pipe，TUI 录制会失真。修复: pip install pywinpty{RESET}", flush=True)
            _WARNED_NO_PTY = True
        _run_exec_piped(program, conn, timeout_s)


def _echo_visible_text(text):
    for line in text.splitlines():
        if line.strip():
            print(line)


def _run_shell_builtin(cmd, conn):
    stripped = cmd.strip()
    if stripped.startswith("cd "):
        target = stripped[3:].strip().strip("'\"")
        try:
            new_dir = os.path.normpath(os.path.join(CWD, os.path.expanduser(target)))
            if os.path.isdir(new_dir):
                globals()["CWD"] = new_dir
                print(f"{GREEN}$ {cmd}{RESET}")
                if SHELL_PROC is not None and SHELL_PROC.poll() is None:
                    _shutdown_shell()
                send_response(conn, "")
            else:
                send_response(conn, f"Error: directory not found: {new_dir}")
        except Exception as e:
            send_response(conn, f"Error: {e}")
        return True
    return False


def _shutdown_pty():
    global PTY_PROC
    if PTY_PROC is not None:
        PTY_PROC.terminate()
        PTY_PROC = None


def _shutdown_shell():
    global SHELL_PROC
    if SHELL_PROC is not None:
        if SHELL_PROC.stdin is not None:
            SHELL_PROC.stdin.close()
        if SHELL_PROC.poll() is None:
            SHELL_PROC.terminate()
    SHELL_PROC = None


def _classify(cmd):
    """从原始 wire 串解析出 (命令类型, 生效 timeout_ms)，作事件日志的可读基线字段。

    生效 timeout = 命令显式给的、否则该类命令的服务端默认；无 timeout 语义的命令返回 None。
    与 handle_cmd 用同一套 _parse_timeout/DEFAULT_* 常量，保证记录的就是实际生效值。
    """
    if cmd.startswith("#EXEC:"):
        return "EXEC", round(_parse_timeout(cmd[6:], DEFAULT_EXEC_TIMEOUT_MS)[1] * 1000)
    if cmd.startswith("#TYPE:"):
        return "TYPE", round(_parse_timeout(cmd[6:], DEFAULT_TYPE_TIMEOUT_MS)[1] * 1000)
    if cmd == "#VIEW" or cmd.startswith("#VIEW "):
        return "VIEW", round(_parse_timeout(cmd[5:], 0)[1] * 1000)
    if cmd.startswith("#ECHO:"):
        return "ECHO", None
    if cmd == "#WAITPROC":
        return "WAITPROC", None
    if cmd == "#EXIT":
        return "EXIT", None
    return "OTHER", None


def handle_cmd(cmd, conn):
    global INTERACTIVE_LOCK, PTY_PROC

    if not cmd or cmd.isspace():
        conn.sendall(b"##END##\n")
        return True

    # 可复现性基线：每条真实命令入口记一次。wire 为原始串(隐含输入)，另补计划要求的
    # kind(命令类型)与 timeout_ms(生效 timeout，含默认值) 作可读基线字段。重放逐条按
    # rel_ms 等待后原样重发 wire 即可复现会话(kind/timeout_ms 仅供观测，不影响重放)。
    if EVENT_LOG is not None:
        kind, eff_timeout_ms = _classify(cmd)
        EVENT_LOG.emit(cmd, kind=kind, timeout_ms=eff_timeout_ms)

    if cmd == "#EXIT":
        conn.sendall(b"#BYE\n")
        _shutdown_pty()
        if _bg_running():
            _shutdown_shell()
        INTERACTIVE_LOCK = False
        return False

    # --- interaction lock check ---
    if INTERACTIVE_LOCK and not cmd.startswith(("#TYPE:", "#VIEW", "#ECHO:", "#WAITPROC", "#EXIT")):
        if cmd.startswith("#EXEC:"):
            send_response(conn, "Error: interaction lock active, use #TYPE/#WAITPROC/#EXIT while process is running")
            return True

    if cmd.startswith("#EXEC:"):
        program, timeout_s = _parse_timeout(cmd[6:], DEFAULT_EXEC_TIMEOUT_MS)
        if _run_shell_builtin(program, conn):
            return True
        _run_exec_command(program, conn, timeout_s)
        return True

    if cmd.startswith("#TYPE:"):
        if not _bg_running():
            send_response(conn, "Error: no interactive process is running")
            return True
        payload, timeout_s = _parse_timeout(cmd[6:], DEFAULT_TYPE_TIMEOUT_MS)
        raw = parse_nvim_tokens(payload)

        if PTY_PROC is not None:
            try:
                for ch in raw:
                    PTY_PROC.write(ch)
                    time.sleep(0.03)
            except (OSError, Exception) as e:
                send_response(conn, f"Error: {e}")
                return True
        else:
            proc = _ensure_shell()
            try:
                for ch in raw:
                    proc.stdin.write(ch.encode("utf-8"))
                    proc.stdin.flush()
                    time.sleep(0.03)
            except (OSError, BrokenPipeError) as e:
                send_response(conn, f"Error: {e}")
                return True

        snap = _wait_and_capture(timeout_s)
        send_response(conn, f"OK:{snap}" if snap else "OK:")
        return True

    if cmd == "#VIEW" or cmd.startswith("#VIEW "):
        if not _bg_running():
            send_response(conn, "Error: no interactive process is running")
            return True
        _, timeout_s = _parse_timeout(cmd[5:], 0)
        snap = _wait_and_capture(timeout_s)
        with SHELL_LOCK:
            header = json.dumps(change_metrics.metrics(list(DIRTY_LOG), time.time()), separators=(",", ":"))
        send_response(conn, f"OK:{header}\n{snap}" if snap else f"OK:{header}")
        return True

    if cmd.startswith("#ECHO:"):
        text = cmd[6:]
        _echo_visible_text(text)
        send_response(conn, f"OK:ECHO:{len(text)} chars")
        return True

    if cmd == "#WAITPROC":
        if PTY_PROC is not None:
            if not PTY_PROC.isalive():
                INTERACTIVE_LOCK = False
                PTY_PROC = None
                send_response(conn, "OK:done")
            else:
                send_response(conn, "OK:running")
        elif SHELL_DONE.is_set() or not _bg_running():
            INTERACTIVE_LOCK = False
            send_response(conn, "OK:done")
        else:
            send_response(conn, "OK:running")
        return True

    if _run_shell_builtin(cmd, conn):
        return True

    print(f"{GREEN}$ {cmd}{RESET}")
    try:
        result = _run_captured_command(cmd)
        output = result.stdout
        if result.stderr:
            output += result.stderr
        if output.strip():
            print(output.rstrip())
        send_response(conn, output.rstrip() if output.strip() else "")
    except subprocess.TimeoutExpired:
        send_response(conn, "Error: command timed out (30s)")
    except Exception as e:
        err = f"Error: {e}"
        print(f"{RED}{err}{RESET}")
        send_response(conn, err)
    return True


def _bg_running():
    if PTY_PROC is not None:
        return PTY_PROC.isalive()
    return SHELL_PROC is not None and SHELL_PROC.poll() is None


def _which(name):
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if os.path.isfile(os.path.join(d, name)):
            return True
    return False


def init_runtime():
    """初始化运行时：探测录制控制台真实尺寸 → 对齐 pyte → 起变化采样线程。

    供 server(accept 循环)与 replay CLI(直接重执行命令)共用同一套运行时，
    保证重放时的尺寸/采样与正常录制一致。幂等：pyte 屏已存在则不重建。
    """
    global PYTE_SCREEN, PYTE_STREAM, SCREEN_COLS, SCREEN_ROWS
    # 尺寸对齐(见 #7)：优先探测本进程 stdout 的真实控制台尺寸(即录制控制台)。
    try:
        real = os.get_terminal_size(sys.stdout.fileno())
        if real.columns > 0 and real.lines > 0:
            SCREEN_COLS, SCREEN_ROWS = real.columns, real.lines
            print(f"{GRAY}detected recording console size: {SCREEN_COLS}x{SCREEN_ROWS}{RESET}", flush=True)
    except OSError:
        pass
    if _PYTE_AVAILABLE and PYTE_SCREEN is None:
        PYTE_SCREEN = pyte.Screen(SCREEN_COLS, SCREEN_ROWS)
        PYTE_STREAM = pyte.Stream(PYTE_SCREEN)
    if PYTE_SCREEN is not None:
        PYTE_SCREEN.dirty.clear()  # 清掉 pyte 新建时的一次性整屏初始脏，再开采样
        threading.Thread(target=_dirty_sampler, daemon=True).start()


def main():
    init_runtime()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", PORT))
    srv.listen(1)
    print(f"{GRAY}TCP server listening on localhost:{PORT}{RESET}")

    try:
        while True:
            conn, _ = srv.accept()
            try:
                data = b""
                while b"\n" not in data:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                cmd = data.decode("utf-8").split("\n")[0].rstrip("\r")
                if not handle_cmd(cmd, conn):
                    break
            except Exception as exc:
                import traceback
                err_msg = traceback.format_exc()
                print(f"{RED}handle_cmd exception: {exc}{RESET}", flush=True)
                err_log = DEBUG_LOG_PATH.parent / "server-error.log"
                with err_log.open("a", encoding="utf-8") as ef:
                    ef.write(f"--- {time.time()} ---\n{err_msg}\n")
            finally:
                conn.close()
    except KeyboardInterrupt:
        pass
    finally:
        srv.close()
        _shutdown_pty()
        _shutdown_shell()
        print(f"{GRAY}Server stopped.{RESET}")


def build_parser():
    parser = argparse.ArgumentParser(description="Compatibility parser for tcp-server entrypoint")
    parser.add_argument("--port", type=int, default=9999)
    parser.add_argument("--cwd", help="Working directory for recorded commands")
    parser.add_argument("--cols", type=int, default=200)
    parser.add_argument("--rows", type=int, default=60)
    parser.add_argument("--events", help="会话事件日志(JSONL)路径；缺省写入 .claude-testing/session-events.jsonl。重放据此复现会话")
    return parser


def main_compat() -> int:
    global PORT, SCREEN_COLS, SCREEN_ROWS, PYTE_SCREEN, PYTE_STREAM, CWD
    args = build_parser().parse_args()
    PORT = args.port
    SCREEN_COLS = args.cols  # 回退默认；init_runtime 会探测真实控制台尺寸并覆盖(见 #7)
    SCREEN_ROWS = args.rows
    if args.cwd:
        cwd_path = Path(args.cwd).expanduser().resolve()
        if cwd_path.is_dir():
            CWD = str(cwd_path)
        else:
            print(f"{RED}Warning: --cwd path does not exist, using current directory{RESET}")
    # pyte 屏由 init_runtime 在探测到真实控制台尺寸后创建(见 #7)，此处不再预建。
    # 打开会话事件日志(截断)。默认落在 repo/.claude-testing/session-events.jsonl；
    # 录制端可传 --events 指向随 cast 走的路径(后续可让 recorder 按 cast 派生)。
    global EVENT_LOG
    events_path = args.events or str(Path(__file__).resolve().parents[2] / ".claude-testing" / "session-events.jsonl")
    try:
        EVENT_LOG = EventLog(events_path).open()
        print(f"{GRAY}session event log: {events_path}{RESET}", flush=True)
    except OSError as e:
        print(f"{RED}[!] 事件日志打开失败({e})，本次不记录、无法重放{RESET}", flush=True)
        EVENT_LOG = None
    main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main_compat())
