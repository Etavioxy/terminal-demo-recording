# observability_replay

可观测性 + 可复现性（重放）的纯单测。对应计划 `implementation-phases-v1.0.md` Phase 7
与 `protocol-v1.0-plan.md` §10 中"可复现性是可观测性的固有属性"。

## 模块（分文件、低耦合）

| 文件 | 职责 | 依赖 |
|---|---|---|
| `src/server/event_log.py` | 生产端：每条进来的命令写一行 JSONL（seq/ts/rel_ms/wire + kind/timeout_ms + 可选诊断）。时钟注入。 | 仅 stdlib |
| `src/replay.py` | 消费端 + CLI：读 event.jsonl → 逐条按 rel_ms 等待后重发。load_commands/replay 纯逻辑(send/sleep 注入)；CLI 用 `make_server_send` 直接调 `handle_cmd`。 | stdlib +(CLI 时)server.app |
| `src/server/app.py` | 集成：`handle_cmd` 入口 `EVENT_LOG.emit(cmd, kind, timeout_ms)`；`_classify` 解析基线字段；`init_runtime` 供 server 与 replay 共用。 | event_log |

生产/消费两端**经 JSONL 文本格式解耦**。

## 基线字段（可复现性，始终记）

`seq`(序号) / `ts` / `rel_ms`(距上一条) / `wire`(原始命令串) / `kind`(类型) / `timeout_ms`(生效 timeout，含默认值)。
对应计划要求的"序号/类型/原始输入/生效timeout/相对时序"——只是承载在 JSONL、且原始输入以整条 wire 保留。

## 重放：独立 CLI、不经 proxy

```powershell
# 通常由录制器包起来，把复现过程录进新 cast：
PowerSession rec -f --stdin -c "py -3 src/replay.py <events.jsonl>" recordings/replay.cast
```
`replay.py` 的 CLI 用 `make_server_send()` → `init_runtime()` + 逐条 `handle_cmd(wire, DummyConn)`，
**在本进程内直接重执行命令**（启动 nvim/输入/退出真实发生），输出被外层录制器录下。
命令级"基本稳定复现"，不逐字节。**不经 proxy/TCP**。

## 与原计划的偏离（有意，已记录）

- **格式**：计划是"文本日志 + TIME/SIZE/STATE 模块 + `#CONFIG` 开关"；本实现用 **JSONL**（更利于机器重放），
  且**暂未实现 TIME/SIZE/STATE 诊断模块与 `#CONFIG`**（后续可作观测增强补上）。
- **重放传输**：计划写"逐条经 proxy 重发"；本实现改为**独立 CLI 直接重执行 handle_cmd**（等价复现、更简单、少一层传输）。
- 基线字段与"命令级基本稳定复现"的语义与计划一致。

## 核心设计：记原始 wire 串

可复现性基线不把命令拆字段，而是记**原始 wire 串**（如 `#EXEC:claude timeout=4000`）——
它隐含了命令类型/原始输入/生效 timeout。重放时逐条按 `rel_ms` 等待后**原样重发**即"基本
稳定复现"（命令级，不逐字节；符合计划定义）。逐条驱动、保留时序，不串成一坨，与"禁止预编排
脚本"不冲突。

## 运行

```powershell
py -3 -m pytest src/testing/observability_replay -q
```

覆盖：基线字段(seq/rel_ms/wire)、None 诊断字段过滤、JSONL 一行一事件、load_commands 往返、
重放顺序+逐条等待、max_wait 钳制、空行/无 wire 行忽略。
