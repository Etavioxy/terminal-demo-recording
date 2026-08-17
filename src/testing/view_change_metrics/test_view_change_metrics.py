"""view_change_metrics 单测：用真实 TUI 输出模式驱动 pyte，验证变化指标。

纯单测——虚拟时钟、不起录制。两层：
1. 锁住 pyte.dirty 的基础行为假设（画字/滚动/纯光标移动各脏几行）。
2. 用四个 pattern_* 输出模式，验证 change_rate 的特征与排序符合人眼感知。
"""
from pathlib import Path
import sys

import pyte
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pattern_append_line
import pattern_cycle_one_cell_fast
import pattern_overwrite_one_cell
import pattern_print_lines_fast
import pyte_measure


# ---------- 第 1 层：锁住 pyte.dirty 基础行为 ----------

def _feed(data, rows=24, cols=80):
    screen = pyte.Screen(cols, rows)
    stream = pyte.Stream(screen)
    screen.dirty.clear()
    stream.feed(data)
    return len(screen.dirty)


def test_pyte_dirty_cursor_move_only_is_zero():
    # 纯光标移动（CUP）不画字 -> 不标脏
    assert _feed("\x1b[5;10H") == 0


def test_pyte_dirty_one_char_is_one_row():
    # 写一句话 -> 仅 1 行脏
    assert _feed("hello world") == 1


def test_pyte_dirty_scroll_is_full_screen():
    # 连续换行触发滚动 -> 整屏脏
    assert _feed("\r\n" * 30, rows=24) == 24


# ---------- 第 2 层：四个输出模式的指标特征 ----------

def _log(module):
    return pyte_measure.build_dirty_log(module.emit())


def test_overwrite_one_cell_peak_area_is_one_row():
    log = _log(pattern_overwrite_one_cell)
    # 固定格覆写：面积小——任一采样点最多脏 1 行（其余采样点为 0，事件间空档）
    assert log and max(rows for _, rows in log) == 1


def test_cycle_one_cell_peak_area_is_one_row():
    log = _log(pattern_cycle_one_cell_fast)
    # spinner：高频但单格 -> 峰值面积仍仅 1 行
    assert log and max(rows for _, rows in log) == 1


def test_print_lines_fast_triggers_full_screen_dirty():
    log = _log(pattern_print_lines_fast)
    # 滚动模式：屏幕填满后单次 feed 脏行数应远大于 1
    assert max(rows for _, rows in log) > 1


def test_scroll_rate_far_exceeds_spinner_despite_lower_frequency():
    """面积 vs 频率：spinner 频率更高，但滚动的变化速率应远超它。"""
    scroll = pyte_measure.build_dirty_log(pattern_print_lines_fast.emit())
    spinner = pyte_measure.build_dirty_log(pattern_cycle_one_cell_fast.emit())
    scroll_rate = pyte_measure.change_rate(scroll, pyte_measure.log_end_time(scroll), 1.0)
    spinner_rate = pyte_measure.change_rate(spinner, pyte_measure.log_end_time(spinner), 1.0)
    assert scroll_rate > spinner_rate > 0


def test_recency_profile_settles_after_activity():
    """活动结束后近窗归零、远窗仍有量——'变化轮廓'。"""
    # 先一段快速滚动，再长时间静默
    events = list(pattern_print_lines_fast.emit(period=0.05, count=40))
    events.append((10.0, ""))  # 末尾静默 10s（空 feed，脏=0）
    log = pyte_measure.build_dirty_log(events)
    now = pyte_measure.log_end_time(log)
    r = pyte_measure.rates(log, now)
    assert r[0.1] == 0  # 此刻已静
    assert r[10.0] > 0  # 10s 内有过大量滚动


def test_append_line_rate_below_scroll():
    """周期追加一行的速率应低于快速滚动。"""
    append = pyte_measure.build_dirty_log(pattern_append_line.emit())
    scroll = pyte_measure.build_dirty_log(pattern_print_lines_fast.emit())
    a = pyte_measure.change_rate(append, pyte_measure.log_end_time(append), 10.0)
    s = pyte_measure.change_rate(scroll, pyte_measure.log_end_time(scroll), 10.0)
    assert 0 < a < s
