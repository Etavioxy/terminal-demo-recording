"""输出模式：每隔 period 追加一行文本。

对应"定时日志输出"类场景——周期性冒出一行，每次脏少量行、低速率周期性。
emit() 产出 (dt, data) 事件流（虚拟时钟）；直接运行则按真实时间打到终端肉眼看。
"""
from __future__ import annotations


def emit(period: float = 1.0, count: int = 10):
    """每隔 period 秒追加一行文本。"""
    for i in range(count):
        yield (period, f"log line {i}\r\n")


if __name__ == "__main__":
    import argparse
    import sys
    import time

    ap = argparse.ArgumentParser()
    ap.add_argument("--period", type=float, default=1.0)
    ap.add_argument("--count", type=int, default=15)  # 默认 ~15s
    a = ap.parse_args()
    for dt, data in emit(a.period, a.count):
        time.sleep(dt)
        sys.stdout.write(data)
        sys.stdout.flush()
