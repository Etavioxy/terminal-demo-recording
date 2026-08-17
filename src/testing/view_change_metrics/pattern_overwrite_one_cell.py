"""输出模式：固定格反复覆写同一字符。

对应"光标闪烁"类场景——同一位置反复重画一个字符，每次只脏 1 行、低速率。
emit() 产出 (dt, data) 事件流（虚拟时钟）；直接运行则按真实时间打到终端肉眼看。
"""
from __future__ import annotations

ROW, COL = 12, 40


def emit(period: float = 0.5, count: int = 10):
    """每隔 period 秒在固定格覆写一个字符（在 '|' 与 ' ' 间切换）。"""
    for i in range(count):
        ch = "|" if i % 2 == 0 else " "
        yield (period, f"\x1b[{ROW};{COL}H{ch}")


if __name__ == "__main__":
    import argparse
    import sys
    import time

    ap = argparse.ArgumentParser()
    ap.add_argument("--period", type=float, default=0.5)
    ap.add_argument("--count", type=int, default=30)  # 默认 ~15s
    a = ap.parse_args()
    for dt, data in emit(a.period, a.count):
        time.sleep(dt)
        sys.stdout.write(data)
        sys.stdout.flush()
    sys.stdout.write("\n")
