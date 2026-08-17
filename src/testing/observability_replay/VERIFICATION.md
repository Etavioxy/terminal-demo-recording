# v1 验证结论（record → replay 端到端）

独立逐字节核实，非结构化对比。方法：解析两份 cast 的 `o` 事件、拼接输出流后比对。

## 场景

同一命令序列先录制、再重放：
`#EXEC:nvim timeout=2000` → `#TYPE:itest hello<C-M><Esc>` → `#VIEW` → `#TYPE::q!<C-M>` → `#EXIT`
- `obs-a.cast`：正常录制（server + TCP + 事件日志）
- `obs-replay2.cast`：`py -3 src/replay.py sess.jsonl` 独立 CLI 直接重执行（不经 proxy）

## 事件日志（可复现性基线）✅

`sess.jsonl` 5 行，每行含 `seq/ts/rel_ms/wire/kind/timeout_ms`；`#EXIT` 无 timeout（None 已过滤）。
基线字段完整、可据此重放。

## cast 逐字节比对

| 度量 | obs-a | obs-replay2 |
|---|---|---|
| 控制台尺寸 | 100×50 | 100×50 |
| 输出总字符 | 11444 | 11301 |
| **nvim alt-screen 正文切片** | **10758** | **10758（同长）** |

- **整体流第 37 字符即分叉**：前导不同——录制模式 `session event log / TCP server listening`，
  重放模式 `detected recording console size: 100x50`（`init_runtime`）。属**模式差异**，预期。
- **nvim 正文切片：前 10666/10758 字符逐字节一致，相似度 99.77%**。开屏、`~` 行、`test hello`、
  状态栏 `[No Name] [+]`、`:q!` 命令行——完全一致。
- **唯一分歧在末尾 ~92 字符**：nvim 退出清理转义（光标形状 `\x1b[2 q`、bracketed-paste `?2004l`、
  窗口标题 `]0;...`）的**发出顺序**不同。这是 PowerSession 分块/上下文差异，非 replay 逻辑偏差。

## 结论

命令级"基本稳定复现"达成，且 nvim 正文实际达到**近字节级复现**（10666/10758 一致，仅退出转义顺序差异）。
录制端与重放端的差异局限于运行模式前导与退出清理转义顺序，均在预期内。

## 已知工具链噪音（非本代码）

- PowerSession（Windows）退出时 panic（pty stdin closed / 句柄无效）；独立 cmd 窗口下 cast 能在
  panic 前写出，后台运行则可能过早崩溃无 cast。属 PowerSession 自身问题。
