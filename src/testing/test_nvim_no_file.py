from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from testing.framework import CastFile, Protocol, Recording, Report
from recorder import repo_root


def test_nvim_no_file():
    # 启动录制进程
    Recording.start("recordings/tests/nvim-no-file.cast", out=CastFile, cwd=str(repo_root()), shell="powershell")

    # 发送启动命令
    Protocol.send("#EXEC:nvim timeout=8000")

    # 发送退出按键
    Protocol.send("#TYPE::q<CR> timeout=1500")

    # 等待目标退出
    Protocol.send("#WAITPROC")

    # 结束录制会话
    Protocol.send("#EXIT")

    # 检查协议返回
    assert "OK" in Report.last_response()

    # 简单判定：nvim 空缓冲启动屏幕的标志性文本
    assert CastFile.has_marker("NVIM")
    assert CastFile.has_marker("~")

    # 强判定
    assert CastFile.has_screen_shape(min_lines=5, min_wide_lines=3, min_screen_events=1, min_output_events=3)
