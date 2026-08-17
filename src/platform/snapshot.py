"""Snapshot provider — captures full terminal screen via pyte emulator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SnapshotResult:
    content: str
    width: int = 200
    height: int = 60
    cursor_x: int = 0
    cursor_y: int = 0
    source: str = "pyte_emulator"


def capture_snapshot() -> SnapshotResult:
    """Capture current terminal screen content from pyte emulator."""
    from server.app import PYTE_SCREEN, SHELL_LOCK

    if PYTE_SCREEN is None:
        return SnapshotResult(content="", source="unavailable")

    with SHELL_LOCK:
        lines = PYTE_SCREEN.display
        content = "\n".join(line.rstrip() for line in lines).rstrip("\n")
        cursor_x = PYTE_SCREEN.cursor.x
        cursor_y = PYTE_SCREEN.cursor.y

    return SnapshotResult(
        content=content,
        width=PYTE_SCREEN.columns,
        height=PYTE_SCREEN.lines,
        cursor_x=cursor_x,
        cursor_y=cursor_y,
        source="pyte_emulator",
    )
