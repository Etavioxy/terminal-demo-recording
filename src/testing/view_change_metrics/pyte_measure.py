"""测试侧测量辅助：把 (dt, data) 事件流喂进 pyte，按虚拟时钟建 dirty_log。

聚合（change_rate/cadence/area_peak/rates/metrics）复用生产模块 server.change_metrics，
避免与 server 漂移；本文件只保留"喂 pyte 生成 dirty_log"这个测试 fixture。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 让 `server.change_metrics` 可导入（src 在 .../view_change_metrics 的上两级）
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pyte

from server.change_metrics import (  # noqa: E402  re-export，测试沿用旧调用
    DEFAULT_WINDOWS,
    SAMPLE_INTERVAL_S,
    area_peak,
    cadence,
    change_rate,
    metrics,
    rates,
)

DEFAULT_ROWS = 24
DEFAULT_COLS = 80


def build_dirty_log(events, rows: int = DEFAULT_ROWS, cols: int = DEFAULT_COLS,
                    interval: float = SAMPLE_INTERVAL_S):
    """虚拟时钟 + interval 网格采样，镜像生产的定时采样线程（与 PTY chunk 无关）。

    按 (dt, data) 推进虚拟时间；事件到点才 feed pyte；每跨过一个 interval 网格点，
    就采一次 len(dirty) 并清空——和生产 _dirty_sampler 同一采样规则，只是时钟是虚拟的。
    """
    screen = pyte.Screen(cols, rows)
    stream = pyte.Stream(screen)
    screen.dirty.clear()  # pyte 新建时整屏初始标脏，先清掉这个一次性初始态
    log = []
    vt = 0.0
    next_sample = interval
    for dt, data in events:
        target = vt + dt
        # 先把落在事件时间之前的采样网格点采掉（捕获此前累积的 dirty）
        while next_sample <= target:
            log.append((round(next_sample, 4), len(screen.dirty)))
            screen.dirty.clear()
            next_sample += interval
        vt = target
        stream.feed(data)
    # 末尾再采一格，收掉最后一次 feed 的 dirty
    log.append((round(next_sample, 4), len(screen.dirty)))
    screen.dirty.clear()
    return log


def log_end_time(dirty_log) -> float:
    """dirty_log 的最后时间戳（无记录则 0）。"""
    return dirty_log[-1][0] if dirty_log else 0.0
