# view_change_metrics

`#VIEW` 稳定指数的**变化指标测定**单测。用真实 TUI 输出模式驱动 pyte，验证"屏幕变化"能被正确测量。

纯单测：虚拟时钟、不起录制、快（~0.05s）、确定。实测数据见 [`MEASUREMENTS.md`](MEASUREMENTS.md)。

## 核心思路

`pyte.Screen.dirty` 是终端模拟器内建的"哪些行需重画"集合：画字/擦除/滚动会标脏，**纯光标移动不标脏**。
所以"闪烁/光标移动"天然≈0、"一句话"≈1 行、"滚动"≈整屏——无需自己做网格 diff。

把每次 feed 的变化行数配时间戳记成 `dirty_log`，再按时间窗聚合成 **change_rate（变化行数/秒）**。

## 文件

| 文件 | 作用 |
|---|---|
| `pattern_overwrite_one_cell.py` | 固定格反复覆写一个字符（低速率，每次脏 1 行） |
| `pattern_append_line.py` | 每隔 period 追加一行（低速率周期性） |
| `pattern_print_lines_fast.py` | 快速连续打印多行触发滚动（大面积高速率） |
| `pattern_cycle_one_cell_fast.py` | 单格高频循环字符（高频/小面积，区分频率 vs 面积） |
| `pyte_measure.py` | 喂 pyte → `dirty_log` → `change_rate` 三窗聚合 |
| `test_view_change_metrics.py` | 断言各模式指标特征与排序 |

每个 `pattern_*.py` 统一暴露 `emit(period, count)` 产出 `(dt, data)` 事件流；也可直接运行按真实时间打到终端肉眼看。

## 运行

```powershell
# 跑单测（需 pyte，用 py -3）
py -3 -m pytest src/testing/view_change_metrics -q

# 肉眼看某个输出模式（默认运行 ~15-16s，绝对定位的两个先 cls）
py -3 src/testing/view_change_metrics/pattern_print_lines_fast.py
# 调快慢/时长
py -3 src/testing/view_change_metrics/pattern_print_lines_fast.py --period 0.2 --count 100
```

> 独立运行的默认 `--count` 调成约 15-16s，方便观察 10s 窗的涨落；
> `emit()` 函数默认值另设（小、给单测当 fixture），两者互不影响。

## 验证了什么

1. **pyte.dirty 基础行为**：纯光标移动=0 行、写一句=1 行、滚动=整屏——锁住测量假设，防 pyte 升级悄悄改行为。
2. **指标特征/排序**：
   - 覆写/spinner：每次仅脏 1 行（面积小）
   - 滚动：单次 feed 脏行数 ≫ 1
   - **面积 vs 频率**：spinner 频率更高，但滚动的 change_rate 远超它
   - **变化轮廓**：活动结束后近窗（0.1s）归零、远窗（10s）仍有量

## 度量术语

- `rows_dirty`：单次 feed 的变化行数（`len(pyte.Screen.dirty)`）
- `dirty_log`：`[(t, rows_dirty), ...]` 时间序列
- `change_rate(dirty_log, now, window)`：窗内 Σrows_dirty / window → 变化行数/秒
- 三窗：`0.1s`（此刻在动吗）/ `1s`（最近一秒动过吗）/ `10s`（最近安静没）
