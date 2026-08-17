from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from testing.framework import CastFile, Lookup, Protocol, Recording, Report
from recorder import repo_root


@pytest.mark.parametrize("shell", ["bash", "powershell"])
def test_less(shell):
    # 启动录制进程
    Recording.start("recordings/tests/less.cast", out=CastFile, cwd=str(repo_root()), shell=shell)

    # 发送启动命令
    Protocol.send(f"#EXEC:{Lookup.executable('less')} README.md")

    # 发送退出按键
    Protocol.send("#TYPE:q timeout=1500")

    # 等待目标退出
    Protocol.send("#WAITPROC")

    # 结束录制会话
    Protocol.send("#EXIT")

    # 检查协议返回
    assert "OK" in Report.last_response()

    # 简单判定
    assert CastFile.has_marker("terminal-demo-director")

    # 强判定
    assert CastFile.has_screen_shape(min_lines=3, min_wide_lines=2)