"""Platform backend helpers for the 1.0 protocol core."""

from __future__ import annotations

from dataclasses import dataclass
import subprocess
from typing import Sequence


@dataclass(frozen=True)
class PlatformBackend:
    name: str


def build_backend(name: str = "subprocess") -> PlatformBackend:
    return PlatformBackend(name=name)


def start_process(command: str, cwd: str, env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        command,
        shell=True,
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def run_process(command: str, cwd: str, env: dict[str, str], timeout_ms: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_ms / 1000,
    )


def write_stdin_lines(proc: subprocess.Popen[str], chunks: Sequence[str]) -> None:
    if proc.stdin is None:
        raise RuntimeError("process stdin is unavailable")
    for chunk in chunks:
        proc.stdin.write(chunk)
        proc.stdin.flush()
