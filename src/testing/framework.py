from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from recorder import repo_root


@dataclass
class CastFileRuntime:
    path: str = ""
    exists: bool = False
    output_text: str = ""
    output_event_count: int = 0
    output_bytes: int = 0
    screen_like_event_count: int = 0
    visible_lines: list[str] = field(default_factory=list)
    wide_line_count: int = 0


class CastFileHandle:
    def __init__(self) -> None:
        self.path = ""
        self._runtime: CastFileRuntime | None = None

    def bind(self, path: str) -> None:
        self.path = path
        self._runtime = None

    def _ensure(self) -> CastFileRuntime:
        if self._runtime is not None:
            return self._runtime
        runtime = CastFileRuntime(path=self.path)
        cast_path = Path(repo_root()) / self.path
        if not cast_path.exists():
            self._runtime = runtime
            return runtime
        runtime.exists = True
        raw_parts: list[str] = []
        with cast_path.open("r", encoding="utf-8", errors="replace") as f:
            for idx, line in enumerate(f):
                if idx == 0:
                    continue
                text = line.strip()
                if not text:
                    continue
                try:
                    event = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, list) or len(event) < 3:
                    continue
                if event[1] != "o":
                    continue
                payload = str(event[2])
                runtime.output_event_count += 1
                runtime.output_bytes += len(payload.encode("utf-8", errors="replace"))
                if "\x1b[?1049h" in payload:
                    runtime.screen_like_event_count += 1
                if payload.count("\n") >= 2:
                    runtime.screen_like_event_count += 1
                raw_parts.append(payload)
        runtime.output_text = self._strip_ansi("".join(raw_parts))
        runtime.visible_lines = [
            line for line in runtime.output_text.splitlines() if line.strip()
        ]
        runtime.wide_line_count = sum(
            1 for line in runtime.visible_lines if len(line.strip()) >= 20
        )
        self._runtime = runtime
        return runtime

    def _strip_ansi(self, text: str) -> str:
        text = text.replace("\r", "\n")
        text = re.sub(r"\x1b\][^\x07]*\x07", "", text)
        text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
        text = re.sub(r"\x1b[@-_]", "", text)
        text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
        text = re.sub(r"\n+", "\n", text)
        return text

    def has_marker(self, *markers: str) -> bool:
        rt = self._ensure()
        return any(marker in rt.output_text for marker in markers)

    def has_screen_shape(
        self,
        min_lines: int = 3,
        min_wide_lines: int = 2,
        min_screen_events: int = 0,
        min_output_events: int = 3,
    ) -> bool:
        rt = self._ensure()
        if not rt.exists:
            return False
        if rt.output_event_count < min_output_events:
            return False
        if len(rt.visible_lines) < min_lines:
            return False
        if rt.wide_line_count < min_wide_lines:
            return False
        if rt.screen_like_event_count < min_screen_events:
            return False
        return True

    def output_bytes(self) -> int:
        return self._ensure().output_bytes

    def visible_text(self) -> str:
        return self._ensure().output_text

    def visible_text_preview(self) -> str:
        return self._ensure().output_text[:300]


CastFile = CastFileHandle()


@dataclass
class ProtocolRuntime:
    port: int = 9999
    cwd: str = ""
    responses: list[str] = field(default_factory=list)
    recorder_output_path: str = ""


class RecordingAction:
    def __init__(self) -> None:
        self.runtime = ProtocolRuntime()

    def start(self, path: str, out: CastFileHandle, cwd: str, port: int = 9999, shell: str = "bash") -> None:
        out.bind(path)
        self.runtime.port = port
        self.runtime.cwd = cwd
        self.runtime.responses.clear()
        output_dir = Path(repo_root()) / ".claude-testing"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"recorder-{int(time.time() * 1000)}.log"
        self.runtime.recorder_output_path = str(output_path)
        command = [
            _python_executable(),
            str(Path(repo_root()) / "src" / "recorder.py"),
            path,
            "--cwd",
            cwd,
            "--wait",
            "--wait-timeout",
            "60",
            "--shell",
            shell,
        ]
        if os.name == "nt":
            command.append("--new-window")
        with output_path.open("w", encoding="utf-8", errors="replace") as handle:
            completed = subprocess.run(
                command, cwd=str(repo_root()), stdout=handle, stderr=subprocess.STDOUT, text=True
            )
        if completed.returncode != 0:
            raise RuntimeError(f"recorder start failed: {output_path}")


class ProtocolAction:
    def __init__(self, runtime: ProtocolRuntime) -> None:
        self.runtime = runtime

    def send(self, command: str) -> str:
        result = subprocess.run(
            [
                _python_executable(),
                str(Path(repo_root()) / "src" / "proxy.py"),
                command,
                "--port",
                str(self.runtime.port),
            ],
            cwd=str(repo_root()),
            capture_output=True,
            text=True,
        )
        response = (result.stdout or result.stderr).strip()
        if response:
            self.runtime.responses.append(response)
        if result.returncode != 0:
            raise RuntimeError(response or f"proxy failed: {command}")
        if command.startswith("#EXEC:"):
            response = self._wait_exec_ready(response)
        print(f"PROTOCOL {command} => {response}")
        return response

    def _wait_exec_ready(self, initial_response: str, settle_seconds: float = 3.0) -> str:
        if "OK:RUNNING:" in initial_response or "OK:running" in initial_response:
            time.sleep(settle_seconds)
        return initial_response


class ProtocolReport:
    def __init__(self, runtime: ProtocolRuntime) -> None:
        self.runtime = runtime

    def last_response(self) -> str:
        if not self.runtime.responses:
            return ""
        return self.runtime.responses[-1]

    def all_responses(self) -> list[str]:
        return list(self.runtime.responses)


class CommandLookup:
    def executable(self, program: str) -> str:
        found = shutil.which(program)
        if not found:
            raise RuntimeError(f"executable not found: {program}")
        return found


Recording = RecordingAction()
Protocol = ProtocolAction(Recording.runtime)
Report = ProtocolReport(Recording.runtime)
Lookup = CommandLookup()


def _python_executable() -> str:
    if os.name == "nt":
        return "py"
    return "python3"
