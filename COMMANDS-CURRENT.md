# 命令现状说明（当前实现）

本文档只描述当前已实现行为，不包含未来方案。

## 一、命令入口

- 所有命令统一使用 `#` 前缀，由 tcp-server 解析。
- 文本输入走 `#TYPE`，命令执行统一走 `#EXEC`（含普通 shell、`cd`、TUI/后台）。
- 非 `#` 前缀输入视为无效命令并返回错误。

## 二、特殊命令与当前返回

### 1) `#EXEC:<command>`

- 作用：统一命令执行入口（普通 shell、`cd`、TUI/后台），全部在 PTY 中执行。
- 当前返回：
  - 普通前台命令：返回 stdout/stderr 文本（无输出时为空字符串）
  - 进入 TUI/后台交互：`OK:started pid=<pid> mode=tui`，并附带整屏内容快照
  - 进程仍在运行且等待后续输入：返回整屏快照 + `state=await_input`
  - 执行失败：`Error: ...`
- 返回时机（不按命令类型分流，只按运行状态）：
  - 进程退出时返回
  - 或输出静止一段时间（约 200~300ms 无新字节）且状态稳定时返回
- 说明：
  - 该规则覆盖“非 TUI 但需要继续输入”的命令，不会被错误归类

### 2) `#TYPE:<text>`

- 作用：向当前前台应用逐字输入文本。
- 特殊键转义（采用 nvim 风格记法，写在 `#TYPE` 文本中）：
  - 控制键：`<C-a>`（即 Ctrl+A），同理 `<C-b>` ... `<C-z>`
  - 回车/退出/制表/退格：`<CR>`, `<Enter>`, `<Esc>`, `<Tab>`, `<BS>`
  - 方向与导航：`<Up>`, `<Down>`, `<Left>`, `<Right>`, `<Home>`, `<End>`
  - 删除与插入：`<Del>`, `<Delete>`, `<Insert>`
  - 功能键：`<F1>`~`<F12>`
  - 字面量 `<`：使用 `<LT>`
  - 字面量 `>`：直接写 `>`
  - 大写输入：直接写 `A`，或用 `<S-a>` 表示 Shift+A
  - 兼容：大小写不敏感（如 `<c-a>` 与 `<C-A>` 等同）
- 当前返回：
  - 成功：返回输入后的整屏内容快照（full-screen snapshot）
  - 失败：`Error: ...`

### 3) `#ECHO:<text>`

- 作用：在录制终端输出说明文本（导演注释）。
- 当前返回：
  - 成功：`OK:ECHO:<N> chars`

### 4) `#WAITPROC`

- 作用：轮询后台进程状态。
- 当前返回：
  - 仍在运行：`OK:running pid=<pid>`
  - 已结束：`OK:done`

### 5) `#EXIT`

- 作用：结束 tcp-server 会话。
- 当前返回：
  - `#BYE`

## 三、交互锁（当前行为）

当 `#EXEC` 启动的 TUI 后台进程仍在运行时：

- 仅允许：`#TYPE`, `#ECHO`, `#WAITPROC`
- 其它命令会返回：
  - `Error: interaction lock active, only #TYPE/#ECHO/#WAITPROC allowed while background app is running`

## 四、代理层返回封装（当前行为）

`proxy.py` 会读取 tcp-server 返回，直到终止标记：

- `##END##`：普通响应结束
- `#BYE`：退出响应

中间内容原样拼接后返回给调用方。
