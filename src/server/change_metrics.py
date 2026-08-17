"""变化指标聚合：从 dirty_log [(t, rows_dirty), ...] 按时间窗算指标。

纯函数、仅 stdlib，无副作用——server 与单测共用同一实现，避免漂移。
被测量是 pyte.Screen.dirty 的行数（画字/擦除/滚动标脏，纯光标移动不标脏）。

- rate    = 窗内 Σrows_dirty / 窗秒数      → 变化行数/秒（综合活跃度，判稳看它）
- cadence = 窗内变化次数 / 窗秒数          → 变化次数/秒（频率：多久动一次）
- area_peak = 窗内单帧最大脏行数           → 面积：一次动多大
"""
from __future__ import annotations

DEFAULT_WINDOWS = (0.1, 1.0, 10.0)

# 采样间隔：生产用定时线程、测试用虚拟时钟网格，都按此节奏采样 pyte.dirty，
# 使采样与 PTY chunk 分块无关——实验与生产同源、结果一致。
SAMPLE_INTERVAL_S = 0.05


def _rows_in_window(dirty_log, now: float, window: float):
    return [r for (t, r) in dirty_log if now - window <= t <= now]


def change_rate(dirty_log, now: float, window: float) -> float:
    """窗内 Σrows_dirty / window → 变化行数/秒。"""
    return sum(_rows_in_window(dirty_log, now, window)) / window


def cadence(dirty_log, now: float, window: float) -> float:
    """窗内变化次数(rows>0) / window → 变化次数/秒（频率）。"""
    return sum(1 for r in _rows_in_window(dirty_log, now, window) if r > 0) / window


def area_peak(dirty_log, now: float, window: float) -> int:
    """窗内单帧最大脏行数（面积）；无样本则 0。"""
    rows = _rows_in_window(dirty_log, now, window)
    return max(rows) if rows else 0


def rates(dirty_log, now: float, windows=DEFAULT_WINDOWS) -> dict:
    """各窗的 change_rate，键为窗秒数（便于按窗取值）。"""
    return {w: change_rate(dirty_log, now, w) for w in windows}


def metrics(dirty_log, now: float, windows=DEFAULT_WINDOWS) -> dict:
    """#VIEW 返回头用的结构：三数组按 windows 对齐。"""
    return {
        "win": list(windows),
        "rate": [round(change_rate(dirty_log, now, w), 1) for w in windows],
        "cadence": [round(cadence(dirty_log, now, w), 1) for w in windows],
        "area_peak": [area_peak(dirty_log, now, w) for w in windows],
    }
