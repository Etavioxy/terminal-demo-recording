"""输出模式：单格高频循环字符。

对应"spinner"类场景——同一格高频换字符：频率高但面积小（每次仅脏 1 行）。
用于区分"频率高"与"面积大"——它频率高、面积小，速率应远低于 print_lines_fast。
emit() 产出 (dt, data) 事件流（虚拟时钟）；直接运行则按真实时间打到终端肉眼看。
"""
from __future__ import annotations

ROW, COL = 12, 40
FRAMES = "|/-\\"


def emit(period: float = 0.1, count: int = 40):
    """每隔 period 秒在固定格循环切换 spinner 字符（高频、单格）。"""
    for i in range(count):
        yield (period, f"\x1b[{ROW};{COL}H{FRAMES[i % len(FRAMES)]}")


if __name__ == "__main__":
    import argparse
    import sys
    import time

    ap = argparse.ArgumentParser()
    ap.add_argument("--period", type=float, default=0.1)
    ap.add_argument("--count", type=int, default=160)  # 默认 ~16s
    a = ap.parse_args()
    for dt, data in emit(a.period, a.count):
        time.sleep(dt)
        sys.stdout.write(data)
        sys.stdout.flush()
    sys.stdout.write("\n")
