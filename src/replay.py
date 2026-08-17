"""从 event.jsonl 重放一次历史会话：按原相对时序逐条驱动命令。

命令级"基本稳定复现"——重现命令序列与时序，不追求逐字节一致。
逐条发送(保留 rel_ms 等待)，不串成一坨；与"禁止预编排脚本串联命令"不冲突。

模块解耦：
- 只依赖 event.jsonl 文本格式(event_log 的产物)与一个注入的 send 回调；不 import server/event_log。
- load_commands 是纯函数(可脱离网络/进程单测)；replay 的 send/sleep 均可注入，便于纯单测。
"""
from __future__ import annotations

import json
import time


def load_commands(path):
    """从 event.jsonl 读出可重放序列 [(rel_ms, wire), ...]，按文件顺序。

    纯函数：只读文件、解析 JSON，不发送任何命令。忽略空行与无 wire 的行。
    """
    cmds = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            wire = rec.get("wire")
            if not wire:
                continue
            cmds.append((rec.get("rel_ms") or 0.0, wire))
    return cmds


def replay(path, send, sleep=time.sleep, max_wait_ms=None):
    """逐条重放：对每条命令先按 rel_ms 等待，再用 send(wire) 发送。

    - send(wire): 调用方注入的发送回调(如通过 proxy 客户端发给 server)。
    - sleep: 注入以便测试(默认 time.sleep)。
    - max_wait_ms: 可选，钳制单条等待上限，避免历史里的长空档拖慢重放。
    返回已发送的 wire 列表。
    """
    sent = []
    for rel_ms, wire in load_commands(path):
        wait = rel_ms
        if max_wait_ms is not None:
            wait = min(wait, max_wait_ms)
        if wait > 0:
            sleep(wait / 1000.0)
        send(wire)
        sent.append(wire)
    return sent


class _DummyConn:
    """重放时无客户端接收响应，sendall 直接丢弃。"""

    def sendall(self, data):
        pass


def make_server_send():
    """构造"直接调 server.handle_cmd"的 send（不经 proxy/TCP）。

    先初始化 server 运行时(尺寸探测/pyte/采样)，再返回一个 send(wire) 回调，
    逐条把命令喂给 server 的命令处理逻辑——命令效果(启动 nvim/输入/退出)真实发生，
    输出走 stdout，被外层录制器录进新 cast。响应无人接收，用 _DummyConn 丢弃。
    """
    from server import app

    app.init_runtime()
    conn = _DummyConn()

    def send(wire):
        app.handle_cmd(wire, conn)

    return send


def main(argv=None):
    """独立 CLI：`python src/replay.py <events.jsonl> [--max-wait-ms N]`。

    不经 proxy——直接在本进程内按时序重执行日志里的命令(server.handle_cmd)。
    通常由录制器包起来跑，以便把复现过程录进新的 cast：
      PowerSession rec ... -c "py -3 src/replay.py <events.jsonl>" replay.cast
    """
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="按事件日志重放一次会话(直接重执行，不经 proxy)")
    ap.add_argument("events", help="事件日志(JSONL)路径")
    ap.add_argument("--max-wait-ms", type=float, default=None, help="单条命令等待上限，压缩历史长空档")
    args = ap.parse_args(argv)

    sent = replay(args.events, send=make_server_send(), max_wait_ms=args.max_wait_ms)
    print(f"replayed {len(sent)} commands from {args.events}")
    return 0


if __name__ == "__main__":
    import sys

    # 允许从 src/ 直接运行：把 src 加入路径以便 import server
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    raise SystemExit(main())
