"""输出模式：快速连续打印多行触发滚动。

对应"大面积滚动"类场景——高频打印，屏幕填满后每次滚动脏整屏、大面积高速率。
emit() 产出 (dt, data) 事件流（虚拟时钟）；直接运行则按真实时间打到终端肉眼看。
"""
from __future__ import annotations


def emit(period: float = 0.05, count: int = 40):
    """每隔 period 秒打印一行，快速连续触发滚动。"""
    for i in range(count):
        yield (period, f"output row {i:>3} ........................................\r\n")


if __name__ == "__main__":
    import argparse
    import sys
    import time

    ap = argparse.ArgumentParser()
    ap.add_argument("--period", type=float, default=0.05)
    ap.add_argument("--count", type=int, default=320)  # 默认 ~16s
    a = ap.parse_args()
    for dt, data in emit(a.period, a.count):
        time.sleep(dt)
        sys.stdout.write(data)
        sys.stdout.flush()
