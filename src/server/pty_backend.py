"""Cross-platform PTY backend abstraction.

Provides a unified interface for spawning child processes in a pseudo-terminal,
so child processes always see isatty()=True regardless of platform.

- Windows: ConPTY via pywinpty
- Linux/macOS: Python built-in pty module
"""
from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod


class PtyBackend(ABC):
    """Abstract PTY interface. All platform backends implement this."""

    @abstractmethod
    def spawn(self, cmd: str, *, cwd: str, rows: int, cols: int, env: dict | None = None) -> None:
        """Spawn a child process inside the PTY."""

    @abstractmethod
    def read(self, size: int = 8192) -> str:
        """Read output from the PTY. Returns empty string if no data. Raises EOFError on close."""

    @abstractmethod
    def write(self, data: str) -> None:
        """Write input to the PTY stdin."""

    @abstractmethod
    def isalive(self) -> bool:
        """Check if the child process is still running."""

    @abstractmethod
    def terminate(self) -> None:
        """Kill the child process."""


class WindowsPtyBackend(PtyBackend):
    """ConPTY backend for Windows, using pywinpty."""

    def __init__(self) -> None:
        self._proc = None

    def spawn(self, cmd: str, *, cwd: str, rows: int, cols: int, env: dict | None = None) -> None:
        import winpty
        self._proc = winpty.PtyProcess.spawn(cmd, dimensions=(rows, cols), cwd=cwd, env=env)

    def read(self, size: int = 8192) -> str:
        if self._proc is None:
            raise EOFError("not spawned")
        return self._proc.read(size)

    def write(self, data: str) -> None:
        if self._proc is None:
            raise RuntimeError("not spawned")
        self._proc.write(data)

    def isalive(self) -> bool:
        if self._proc is None:
            return False
        return self._proc.isalive()

    def terminate(self) -> None:
        if self._proc is not None:
            try:
                if self._proc.isalive():
                    self._proc.terminate()
            except Exception:
                pass
            self._proc = None


class UnixPtyBackend(PtyBackend):
    """PTY backend for Linux/macOS, using Python's built-in pty module."""

    def __init__(self) -> None:
        self._master_fd: int | None = None
        self._pid: int | None = None

    def spawn(self, cmd: str, *, cwd: str, rows: int, cols: int, env: dict | None = None) -> None:
        import pty
        import fcntl
        import struct
        import termios

        master_fd, slave_fd = pty.openpty()

        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

        pid = os.fork()
        if pid == 0:
            os.setsid()
            fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            os.close(master_fd)
            os.close(slave_fd)
            os.chdir(cwd)
            if env:
                os.environ.update(env)
            os.execvp("/bin/sh", ["/bin/sh", "-c", cmd])

        os.close(slave_fd)
        self._master_fd = master_fd
        self._pid = pid

    def read(self, size: int = 8192) -> str:
        if self._master_fd is None:
            raise EOFError("not spawned")
        try:
            data = os.read(self._master_fd, size)
        except OSError:
            raise EOFError("pty closed")
        if not data:
            raise EOFError("pty closed")
        return data.decode("utf-8", errors="replace")

    def write(self, data: str) -> None:
        if self._master_fd is None:
            raise RuntimeError("not spawned")
        os.write(self._master_fd, data.encode("utf-8"))

    def isalive(self) -> bool:
        if self._pid is None:
            return False
        try:
            pid, status = os.waitpid(self._pid, os.WNOHANG)
            if pid == 0:
                return True
            self._pid = None
            return False
        except ChildProcessError:
            self._pid = None
            return False

    def terminate(self) -> None:
        import signal
        if self._pid is not None:
            try:
                os.kill(self._pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            self._pid = None
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None


def create_backend() -> PtyBackend | None:
    """Create the appropriate PTY backend for the current platform.
    Returns None if no PTY implementation is available.
    """
    if os.name == "nt":
        try:
            import winpty  # noqa: F401
            return WindowsPtyBackend()
        except ImportError:
            return None
    else:
        try:
            import pty  # noqa: F401
            return UnixPtyBackend()
        except ImportError:
            return None
