from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from testing.framework import CastFile, Protocol, Recording, Report
from recorder import repo_root


@pytest.mark.parametrize(
    "mode, cast_name, visible_marker",
    [
        ("empty_buffer_path", "rust-tui-empty-buffer.cast", "Empty buffer startup screen"),
        ("file_buffer_path", "rust-tui-file-buffer.cast", "example_buffer.txt"),
    ],
)
def test_rust_tui(mode, cast_name, visible_marker):
    rust_demo_dir = Path(repo_root()) / "src" / "testing" / "rust-tui-demo"
    exe_path = rust_demo_dir / "target" / "release" / "rust-tui-demo.exe"

    Recording.start(f"recordings/tests/{cast_name}", out=CastFile, cwd=str(rust_demo_dir), shell="powershell")
    Protocol.send(f"#EXEC:{exe_path} {mode} timeout=5000")
    Protocol.send("#WAITPROC")
    Protocol.send("#EXIT")
    assert "OK" in Report.last_response()
    assert CastFile.has_marker("$qm")
    if mode == "empty_buffer_path":
        assert not CastFile.has_marker(visible_marker)
        assert not CastFile.has_marker("example_buffer.txt")
    if mode == "file_buffer_path":
        assert CastFile.has_marker(visible_marker)
        assert CastFile.has_screen_shape(min_lines=3, min_wide_lines=2, min_screen_events=1)
        assert not CastFile.has_marker("Empty buffer startup screen")
        assert CastFile.has_marker("0,0-1          All")
