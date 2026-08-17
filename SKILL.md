---
name: terminal-demo-recording
description: 使用 TCP 代理 + PowerSession 录制 AI 终端操作为 .cast 文件。适用于用户要求录制 demo、展示 AI 终端操作、生成 asciinema 回放、或需要可视化证明 AI 执行过程的场景。
---

# Terminal Demo Recording

通过 TCP 透明代理让 AI 命令在 PowerSession 录制的终端中执行，生成 asciinema v2 格式 .cast 文件。

## 核心概念

- **TCP 代理**：AI 调用 proxy 脚本和直接执行命令返回完全一致，但背后在录制终端中执行
- **录制终端**：录制器创建终端运行 tcp-server，捕获所有终端输出
- **.cast 文件**：asciinema v2 JSON Lines 格式，可用 asciinema-player 回放

## 平台差异

仅录制器不同：
- **Windows**：PowerSession-rs（`cargo install PowerSession`）
- **Linux/macOS**：asciinema（`pip install asciinema` 或系统包管理器）

其他组件跨平台统一：`src/recorder.py`、`src/tcp-server.py`、`src/proxy.py`、stdin pipe 驱动 TUI 输入。

## 录制流程

### 1. 启动录制

**Windows**（PowerSession，必须在独立窗口中）：

```powershell
# 在本 skill 仓库（SKILL.md 所在目录）执行
py -3 src/recorder.py recordings/<project-slug>/demo.cast --cwd <项目路径> --new-window --wait
```

**Linux / macOS**（asciinema，在另一个终端中）：

```bash
# 在本 skill 仓库（SKILL.md 所在目录）执行
python3 src/recorder.py recordings/<project-slug>/demo.cast --cwd <项目路径> --wait
```

**参数说明**：
- `--cwd <项目路径>`：录制命令执行的工作目录（被 demo 的项目目录）
- `<project-slug>`：被 demo 的项目名称（如 `clawd-chat`）

### 2. 发送命令

```powershell
# 在本 skill 仓库执行
py -3 src/proxy.py '#ECHO:demo start'
```

```bash
# 在本 skill 仓库执行
python3 src/proxy.py '#ECHO:demo start'
```

### 3. TUI 交互（逐字输入）

tcp-server 当前支持以下特殊命令前缀，用于控制 TUI 应用（如 vim、htop 等）：

| 前缀 | 用途 | 示例 |
|------|------|------|
| `#EXEC:` | 在录制终端中启动后台进程 | `py -3 src/proxy.py '#EXEC:vim fib.py'` |
| `#TYPE:` | 逐字输入文本（30ms/字），返回输入后整屏快照 | `py -3 src/proxy.py '#TYPE:ihello<CR><Esc>'` |
| `#VIEW` | 只读取屏：返回稳定指数 JSON 头 + 当前整屏快照（默认立即抓，可 `#VIEW timeout=500`） | `py -3 src/proxy.py '#VIEW'` |
| `#ECHO:` | 输出说明文本（返回简短确认） | `py -3 src/proxy.py '#ECHO:>> Step 2'` |
| `#WAITPROC` | 查询后台进程是否结束 | `py -3 src/proxy.py '#WAITPROC'` |

`#VIEW` 用于在不打扰 TUI 的前提下观察异步/流式渲染（如 Claude/ink 流式输出）：`#WAITPROC` 只告诉你 running/done，要看屏幕内容用 `#VIEW` 轮询。

返回首行是稳定指数 JSON，随后是整屏快照：

```
OK:{"win":[0.1,1,10],"rate":[..],"cadence":[..],"area_peak":[..]}
<整屏快照>
```

三数组按 0.1/1/10s 三窗对齐：`rate`=变化行数/秒（综合活跃度，判稳看它）、`cadence`=变化次数/秒（频率）、`area_peak`=窗内单帧最大脏行数（面积）。三窗都≈0 表示画面已稳、这帧快照可信。

`#TYPE:` 内支持 nvim 风格 token：`<CR>`, `<Enter>`, `<Esc>`, `<Tab>`, `<BS>`, `<Up>`, `<Down>`, `<Left>`, `<Right>`, `<Home>`, `<End>`, `<Del>`, `<Delete>`, `<Insert>`, `<LT>`, `<C-x>`。

**典型 Vim 操作流程**：

```powershell
# 1. 启动 vim
py -3 src/proxy.py '#EXEC:vim myfile.py'

# 2. 用 #VIEW 确认 vim 已稳定
py -3 src/proxy.py '#VIEW'

# 3. 进入插入模式
py -3 src/proxy.py '#TYPE:i'

# 4. 逐行输入代码（每行后按 Enter）
py -3 src/proxy.py '#TYPE:print("hello")<Enter>'
py -3 src/proxy.py '#TYPE:print("world")<Enter>'

# 5. 退出插入模式 + 保存退出
py -3 src/proxy.py '#TYPE:<Esc>'
py -3 src/proxy.py '#TYPE::wq<Enter>'

# 6. 等待 vim 退出
py -3 src/proxy.py '#WAITPROC'
```

**注意事项**：
- `#TYPE:` 的第一个字符就是输入内容（不要加空格）
- nvim 风格 token（如 `<Enter>`、`<Esc>`）会自动解析为实际按键
- vim 插入模式下，`<Enter>` 创建新行
- `#EXEC:` 通过持久 shell 执行，stdin pipe 驱动 TUI 输入
- nvim 风格 token（如 `<Enter>`、`<Esc>`、`<C-a>`）直接嵌入 `#TYPE:` 文本中
- 当 `#EXEC:` 启动的后台进程仍在运行时，tcp-server 进入交互锁，只允许 `#TYPE/#VIEW/#ECHO/#WAITPROC/#EXIT`
- 当场景要求稳定触发侧栏开关，优先 `#TYPE:<F2>`（含回退）或 `#TYPE:<C-B>`

### 4. 停止录制

```powershell
# 在本 skill 仓库执行
py -3 src/proxy.py '#EXIT'
```

### 5. 播放

```powershell
# 在本 skill 仓库执行
cd player && npm install && npm run dev
```

打开 `http://localhost:8765`，在左侧列表选择对应项目即可播放。

**直接链接**：也支持通过 query 参数直接访问指定 cast 文件：

```
http://localhost:8765/?project=<project-slug>&cast=<file>.cast
```

例如：

```
http://localhost:8765/?project=recordings-demo&cast=vim-fibonacci-demo.cast
http://localhost:8765/?project=recordings/codediff-universe-path&cast=exp06-demo.cast
```

## 关键约束

1. **Windows：PowerSession 必须在独立窗口中运行**（不能在 Cursor shell 中，会因无 console 导致 stdout writer panic）
2. **Linux/macOS：asciinema 在另一个终端中运行**（或通过 tmux/screen 分离）
3. **每次 TCP 连接只处理一个命令**（server 是单连接顺序处理）
4. **空命令会被忽略**（端口检查连接不会消耗 server accept）
5. **stdout/stderr 合并输出**（跨平台统一）
6. **会话状态持久化**（持久 shell，变量在多次命令之间保持）
7. **冷启动**：Windows 约 10-15 秒（PowerSession + PowerShell），Linux/macOS 约 1-2 秒（asciinema + Python）
8. **`recordings-demo/` 只读**：该目录仅存放仓库内置示例，禁止写入新的项目录制文件
9. **项目录制必须按项目分目录**：新录制必须写入 `recordings/<project-slug>/`
10. **项目一致性约束**：`project-slug` 必须与当前演示项目一致（例如 `<project-slug>` 项目写入 `recordings/<project-slug>/`）
11. **后台交互锁约束**：后台应用运行期间，禁止普通命令直出；需要注释时使用 `#ECHO:`
12. **禁止 Sleep 等待**：录制过程中不得使用 `Start-Sleep` 或任何形式的手动延迟等待。应多使用 `#VIEW` 主动获取交互状态，通过交互驱动流程而非被动等待。

## AI 录制指导

### 录制前：规划展示

在发送第一条命令之前，必须完成规划：

1. **展示重点**：明确 1-3 个核心能力。每个能力 = 一个"场景"
2. **场景脚本**：为每个场景列出：注释文本 → 命令 → 期望输出要点 → AI 总结语
3. **预估时长**：每个场景 10-20 秒。启动冷启动 10-15 秒不算在内（播放器 idleTimeLimit 跳过）
4. **语言规则**：所有注释和强调文本使用**用户的语言**（中文/英文），与用户对话时保持一致
5. **导演思维**：不止展示命令结果的摘要——至少选一个数据点，展示它的来龙去脉（细节）

### 叙事连贯性：讲一个完整的故事

Demo 不是独立步骤的堆砌。观众需要看到因果链：**为什么做 → 怎么做 → 做了什么 → 验证结果**。

**规则**：

1. **每步衔接上一步的输出**。Step N 的输入应该来自 Step N-1 的产出。
   - ❌ 独立展示：`init → apply → verify`（三个孤立动作）
   - ✅ 连贯叙事：`init → 查看生成了什么数据 → 用这些数据 apply → 打开文件看变化 → verify 确认一致性`
2. **过渡句必须解释"为什么下一步"**：用 `#ECHO` 在步骤之间添加转场注释。
   - 例：`"刚才生成了 61 条 marker 记录，来看看其中一条长什么样"`
3. **回溯验证**：至少一个步骤需要"回头看"——对比操作前后的同一位置，而非只看最终结果。

**泛化模板**（适用于任何工具 demo）：

```
Act 1 — 初始化   ：工具从零开始，展示初始状态
Act 2 — 数据生成 ：工具产出数据，展示数据的结构和内容
Act 3 — 核心动作 ：用数据驱动变更，展示变更前后对比
Act 4 — 验证     ：检查变更是否正确，展示健康度/覆盖率等指标
Act 5 — 回退/清理：证明操作可逆/幂等
```

不是每个 Act 都必须存在，但 **Act 2（数据展示）和 Act 3（变更对比）是必须的**。

### 数据透明度：展示底层数据长什么样

观众不仅需要知道"生成了 61 条记录"，还需要看到**一条记录的真实结构**。

**规则：每次录制至少有 1 个"打开数据"场景**，用命令行工具打印出底层数据文件的实际内容。

**执行方法**：

```
1. 找到工具产出的数据文件（JSON/JSONL/TOML/YAML 等）
2. 用 Get-Content + Select-Object 取出 1-3 条记录
3. 用 AI 注释高亮关键字段，解释每个字段的含义
4. 将数据中的某个字段（如 file_path）与实际文件内容对照
```

**时间控制**：数据展示场景预算 10-15 秒。只展示一条记录的核心字段，不要全量打印。

**格式化技巧**：
- JSON/JSONL 必须 pretty-print：`ConvertFrom-Json | ConvertTo-Json -Depth 3`
- 太长时用 `Select-Object` 过滤关键属性：`ConvertFrom-Json | Select-Object file, method, hash | ConvertTo-Json`
- 单行 JSONL 对观众是不可读的——永远不要直接展示原始 JSON 单行
- 用 ANSI 色彩高亮字段名，让观众一眼抓住重点

### 转换链路：展示 "数据 → 变更" 的映射

观众需要看到：**这条数据 → 驱动了这段代码的变化**。

**规则**：至少有 1 个场景展示从数据记录到实际变更的完整链路。

**泛化模板**：

```
1. 展示数据记录中的关键信息（例：file=X, line=Y, original_code, variant_code）
2. 打开目标文件 X 的第 Y 行附近，展示当前代码（= original_code）
3. 执行变更操作
4. 再次打开同一位置，展示变更后的代码（= variant_code）
5. 用 AI 注释标注 "看到了吗？这行从 A 变成了 B"
```

**重要**：不要只展示"前"和"后"——必须在展示"前"的时候告诉观众"接下来这里会变"，这样观众才知道往哪儿看。

**代码对比技巧**：
- 展示代码时用 `Get-Content file.cs | Select-Object -Skip $start -First $count` 精确定位
- 用 ANSI 色彩区分：原始代码用普通白色，变更后的代码用黄色或绿色高亮
- 控制在 3-8 行，多了观众来不及消化

### 导演行为：展示数据细节（深入场景）

以上三个规则（叙事连贯、数据透明、转换链路）的综合实践。

**规则：每次录制至少有 1 个"深入展示"场景**，把叙事线拉到具体数据层面。

泛化示例：

```
场景 A：展示一条数据记录的完整生命周期
  1. 从数据文件中挑出一条记录，打印关键字段（数据透明度）
  2. 展示该记录对应的源文件中的代码（转换链路 - 前）
  3. 执行变更操作（核心动作）
  4. 展示同位置的变更后代码（转换链路 - 后）
  5. 用注释总结："这条记录控制了这 N 行代码的切换"

场景 B：展示一个验证不通过的案例
  1. 从验证输出中挑一个失败/低分的条目
  2. 打印该条目的标识信息和期望值
  3. 用命令行工具展示实际文件中的对应位置
  4. 用注释解释不匹配的原因
```

**时间控制**：深入展示场景预算 15-25 秒。通过 `Get-Content -TotalCount 5` 或 `Select-Object -First 3` 控制输出量。

**选择标准**：
- 挑有代表性的数据（不是边缘情况）
- 展示的代码片段控制在 3-8 行
- 用 AI 注释说明观众应该关注什么

### 录制中：逐步执行

**每一步必须是独立的 proxy.py 调用。** 每一步之间 AI 必须检查返回值。

```
❌ 错误：一个 Shell 调用发出全部命令（观众看到信息洪流）
✅ 正确：每步一个 Shell 调用，检查输出，构造下一步
```

**每步结构**（严格按顺序）：

```
1. 场景注释  →  #ECHO 彩色标题（告诉观众"接下来要做什么"）
2. 停顿       →  Start-Sleep 500ms（让观众读注释）
3. 执行命令  →  实际操作命令
4. 检查输出  →  AI 读取返回值，确认无误
5. AI 总结   →  #ECHO 彩色高亮摘要（告诉观众"刚才发生了什么"）
6. 停顿       →  Start-Sleep 800ms-1s（让观众消化）
```

### 注释色彩系统

| 颜色 | ANSI 码 | 用途 | 示例 |
|------|---------|------|------|
| Cyan FG | 36 | 场景标题文字 | `[Step 1] Initialize marker store` |
| Cyan BG | 46;30 | 场景标题反色 | 白底黑字高亮条 |
| Yellow | 33 | 关键结果高亮 | `>> Generated 61 markers in 696ms!` |
| Green | 32 | 命令回显/成功 | `PS> udm init` |
| Magenta | 35 | 数据摘要 | `50 method + 11 header` |
| DarkGray | 90 | 上下文/分隔线 | `Working dir: D:\project` |

**跨平台色彩兼容性**：

使用 `#ECHO` + ANSI escape 是唯一跨平台一致的方案，不依赖特定 shell 的内置命令。
返回值简短，不污染控制流。

bash 示例：

```bash
echo -e "\e[46;30m [Step 1] Title \e[0m"
echo -e "\e[33m>> Key result\e[0m"
echo -e "\e[32mPS> command\e[0m"
```

**重要：tcp-server 的重打印陷阱**

该陷阱只发生在“普通命令执行路径”（`Invoke-Expression`）：
tcp-server 会把命令输出再打印一次，可能造成颜色降级或重复视觉噪音。
使用 `#ECHO:` 不走这条路径，因此不会触发该问题。

**解决方案**：注释文本统一走 `#ECHO:`，并在 `#ECHO` 文本里使用 ANSI。

```powershell
$e = [char]27

# ✅ 正确：注释统一走 #ECHO，返回值仅为 OK:ECHO:<n> chars
py -3 src/proxy.py "#ECHO:$e[46;30m [Step 3] 验证 marker 健康度 $e[0m"
py -3 src/proxy.py "#ECHO:  $e[32mPS> udm verify$e[0m"
py -3 src/proxy.py "#ECHO:  $e[33m>> 健康度: 60.0% — 30/50 精确匹配$e[0m"
py -3 src/proxy.py "#ECHO:  $e[90m$('=' * 46)$e[0m"

# ❌ 不推荐：注释走普通命令路径，容易触发重打印噪音
py -3 src/proxy.py 'Write-Host "  >> Health: 60.0%" -ForegroundColor Yellow'
```

**ANSI 码速查**：

| 效果 | 代码 | 用法 |
|------|------|------|
| 青色前景 | `$e[36m` | 信息说明 |
| 绿色前景 | `$e[32m` | PS 提示、成功 |
| 黄色前景 | `$e[33m` | 关键结果 |
| 品红前景 | `$e[35m` | 数据摘要 |
| 暗灰前景 | `$e[90m` | 上下文/分隔线 |
| 青色背景+黑字 | `$e[46;30m` | 场景标题 |
| 黄色背景+黑字 | `$e[43;30m` | 操作步骤标题 |
| 重置 | `$e[0m` | 每段结尾必须加 |

### 输出管理

**核心原则：观众需要理解发生了什么，不需要看到全部原始输出。**

**输出长度敏感——AI 必须在发送命令之前预判输出行数：**

| 预判行数 | 策略 |
|----------|------|
| ≤ 5 行 | 直接展示 |
| 5-15 行 | 截断（`Select-Object -First N`）+ AI 彩色总结 |
| 15-30 行 | **抑制原始输出** + AI 用 #ECHO 彩色总结关键数据 |
| > 30 行 | **必须抑制**。如需展示细节，用 clear + 精选几行 |

**预判方法**：根据对命令输出的了解（help 输出、verify 输出等）提前决定策略。不确定时，先在 AI 侧静默运行 (`$null = ...`)，检查行数后再决定怎么展示。

**禁止重复原始输出**：AI 展示的彩色注释必须是**描述性的**，用用户语言（中文）总结，而不是复制粘贴命令的原始输出。tcp-server 已经打印过一次原始输出了。

```powershell
$e = [char]27

# ❌ 不好：让 24 行 verify 失败条目直接刷屏
py -3 src/proxy.py '& $udm verify'

# ❌ 不好：抑制后又复制粘贴英文原始输出
$r = py -3 src/proxy.py '$null = & $udm verify 2>&1 | Out-String; "done"'
py -3 src/proxy.py "Write-Host `"  $e[33m>> Verify complete in 58ms: exact=26$e[0m`""  # 原文重复！

# ✅ 好：抑制输出 + 用用户语言描述性总结
$r = py -3 src/proxy.py '$null = & $udm verify 2>&1 | Out-String; "done"'
py -3 src/proxy.py "#ECHO:  $e[33m>> 26 个精确匹配，健康度 54%$e[0m"  # 描述性中文

# ✅ 好：代码预览也应带色
$code = py -3 src/proxy.py 'Get-Content file.cs -TotalCount 5 | Out-String'
py -3 src/proxy.py "#ECHO:  $e[90m--- file.cs (前5行) ---$e[0m"
```

### Clear 强调

**`Clear-Host`（`cls`）是导演的重要工具**，用于：
- 切换"场景"：清除前一步的输出噪音，给下一步一个干净画布
- 全屏展示：当需要展示大量文本（pretty JSON、代码对比）时，先 clear 再展示
- 聚焦注意力：观众看到清屏后会集中精神

**规则**：

1. **禁止瞬时 clear**：每次 clear 前必须有 **≥ 3 秒延迟**（让观众看完当前内容）
2. **合并命令**：将 sleep + clear 合并为一条 `Start-Sleep -Seconds 3; Clear-Host`，减少 AI 回合开销
3. **clear 后立即输出标题**：清屏后的第一行必须是场景标题，告诉观众"现在看什么"
4. **不要频繁 clear**：每 2-3 个步骤最多 clear 一次，否则观众来不及看
5. **适合 clear 的场景**：展示 pretty JSON、代码对比、大型报告

```powershell
$e = [char]27

# ❌ 不好：瞬时 clear
py -3 src/proxy.py 'Clear-Host'

# ❌ 不好：分开发送（多一次 AI 回合）
py -3 src/proxy.py 'Start-Sleep -Seconds 3'
py -3 src/proxy.py 'Clear-Host'

# ✅ 好：合并为一条命令
py -3 src/proxy.py 'Start-Sleep -Seconds 3; Clear-Host'
py -3 src/proxy.py "#ECHO:$e[46;30m  Marker 数据结构  $e[0m"
```

### 时间控制

| 类型 | 耗时 | 说明 |
|------|------|------|
| 冷启动 | 10-15s | 播放器 idleTimeLimit=3 自动跳过 |
| 场景注释 | 手动 500ms | `Start-Sleep -Milliseconds 500` |
| 命令执行 | 0.1-2s | 本地快，网络慢 |
| 消化停顿 | 手动 800-1000ms | 每步结束后，让观众读完 |
| AI 回合间隔 | 2-5s | 如果太慢，合并多个 proxy.py 调用到同一个 Shell 调用 |

**目标**：每个场景 10-20 秒，总时长 = 场景数 × 15 秒。

### 逐步验证规则

1. 每个 proxy.py 调用后**必须打印返回值到 AI console**（用于验证执行结果）
2. 如果返回值含异常（Error、空值、非预期格式），**立即处理**，不继续下一步
3. 如果需要从返回值中提取数据构造下一步命令，**先在 AI 侧处理**，再发送
4. 录制终端无法撤回已发送的命令——所有错误都会被录制进去

### 错误处理

- 命令失败时不要忽略，展示错误处理过程更真实
- TCP server 返回 `Error: ...` 前缀的消息表示执行失败
- 可以在录制中展示 retry 或 fallback 逻辑

### 字符串安全

- 单引号内的撇号：`-replace "'","''"`
- 双引号内的美元符：`` `$ ``
- 变量嵌入用双引号：`"Today is $date"`
- **换行分割**：避免 `[Environment]::NewLine`（Windows 是 `\r\n`，输出可能只有 `\n`）。改用 `-split "[\r\n]+"` 或 `.Split("`n")`
- **ANSI 字符串中禁止嵌入换行符**：换行用独立 `#ECHO:` 实现，不要在 ANSI escape 字符串内加 `` `n ``（PowerShell）或 `\n`（bash）（会断裂引号）

## 播放

```powershell
# 在本 skill 仓库执行
cd player && npm install && npm run dev
```

打开 `http://localhost:8765`，在左侧列表选择对应项目即可播放。

## 导出 GIF

使用 `agg`（asciinema gif generator）将 `.cast` 文件转为 GIF 图片，方便分享。

**安装**：

```bash
cargo install --git https://github.com/asciinema/agg
```

**转换**：

```powershell
agg --idle-time-limit 2 --fps-cap 15 recording.cast output.gif
```

| 参数 | 作用 | 推荐值 |
|------|------|--------|
| `--idle-time-limit` | 空闲帧最大秒数 | 2-3（压缩 AI 回合间隔，核心参数） |
| `--fps-cap` | 帧率上限 | 15-30（降低帧率减小文件体积） |
| `--last-frame-duration` | 最后一帧停留秒数 | 3（默认） |
| `--cols` / `--rows` | 终端尺寸覆盖 | 默认自动 |
| `--font-size` | 字体大小（像素） | 默认 16 |
| `--theme` | 颜色主题 | asciinema / dracula / monokai / solarized-dark |

**禁止使用 `--speed`**：`--speed` 会加速所有内容（包括打字动画和命令输出），导致录制看起来不自然。正确做法是只用 `--idle-time-limit` 压缩 AI 回合之间的空闲帧，保持操作本身的真实速率。

**典型用法**（导出到桌面）：

```powershell
$desktop = [Environment]::GetFolderPath("Desktop")
agg --idle-time-limit 2 --fps-cap 15 recordings-demo/demo.cast "$desktop\demo.gif"
```

**压缩效果**：AI 录制的 cast 文件通常 50%-80% 是空闲帧（AI 回合间隔 2-5 秒），`--idle-time-limit 2` 可将 3 分钟原始录制压缩到约 1 分钟 GIF，同时保留所有操作的真实节奏。

## 目录结构

```
src/                        ← 源码
  server/app.py                  TCP 服务端核心（Python）
  tcp-server.py                  兼容入口（Python）
  proxy.py                       AI 侧代理（Python）
  recorder.py                    录制启动入口（Python）

player/                     ← Vite + asciinema-player 前端（跨平台）
  index.html                    入口页面
  src/main.js                   播放器逻辑
  src/style.css                 样式
  vite.config.js                构建配置（自动复制 casts）
  package.json                  依赖管理

recordings-demo/            ← 示例录制（入 git）
recordings/                 ← 用户录制（gitignore）
```

## 示例

- `recordings-demo/date-holiday-demo.cast`：AI 获取日期并查询节日（基础 TCP 代理演示）
- `recordings-demo/vim-fibonacci-demo.cast`：AI 在 Vim 中逐字编写斐波那契脚本（TUI 交互演示）

## 依赖

**通用**：
- Node.js + npm：前端播放器构建（`npm install` → `npm run build`）
- Python 3：tcp-server 和 proxy 运行环境
- agg：`cargo install --git https://github.com/asciinema/agg`（GIF 导出，可选）

**Windows**：
- PowerSession-rs：`cargo install PowerSession`

**Linux / macOS**：
- asciinema：`pip install asciinema` 或系统包管理器（`apt install asciinema` / `brew install asciinema`）
