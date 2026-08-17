#!/usr/bin/env python3
"""Compatibility wrapper for the Phase 1 Python server entrypoint."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.app import main_compat


if __name__ == "__main__":
    raise SystemExit(main_compat())
