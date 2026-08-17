from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from testing.framework import CastFile, Lookup, Protocol, Recording, Report
from recorder import repo_root


@pytest.mark.parametrize("shell", ["bash", "powershell"])
def test_yazi(shell):
    Recording.start("recordings/tests/yazi.cast", out=CastFile, cwd=str(repo_root()), shell=shell)

    # yazi 需要 ~15s 完成终端能力检测（Kitty graphics/keyboard 协议查询超时后 fallback）
    Protocol.send(f"#EXEC:{Lookup.executable('yazi')} timeout=20000")

    Protocol.send("#TYPE:q timeout=2000")
    Protocol.send("#WAITPROC")
    Protocol.send("#EXIT")

    assert "OK" in Report.last_response()
    assert CastFile.has_marker("README")
    assert CastFile.has_screen_shape(min_lines=5, min_wide_lines=3, min_screen_events=1, min_output_events=3)