# date-holiday-demo

## 主题
用最短的一段终端演示，展示 AI 先拿到当天日期，再基于这个日期去查询节日数据，最后把信息汇总成一句自然语言结果。

---

## 版本 A：变量批处理

**目标文件：** `recordings-demo/date-holiday-demo-a.cast`

利用 shell 变量持久化，一次性拼好命令发送，不依赖中间输出。

### 步骤
1. 录制终端启动 TCP server，显示 `TCP server listening on localhost:9999`。
2. AI 一条命令获取日期并存入变量：`$date = Get-Date -Format "yyyy-MM-dd"; $dow = Get-Date -Format "dddd"`。
3. AI 一条命令用变量调用 holiday API 并存入变量：`$resp = Invoke-RestMethod "https://timor.tech/api/holiday/info/$date"`。
4. AI 一条命令用变量拼出汇总语句：`Write-Output "Summary: Today is $date ($dow). $($resp.type.name)."`。
5. 演示结束，server 停止。

### 特点
- 每步只发一条 `#EXEC`，不需要读取上一步输出。
- 所有中间数据通过 shell 变量在同一持久会话中传递。
- 画面上只看到命令和最终结果，过程紧凑。

---

## 版本 B：交互逐步

**目标文件：** `recordings-demo/date-holiday-demo-b.cast`

禁止使用变量，每一步都要看到输出，再根据输出内容构造下一条命令。

### 协议流程
```
proxy  →  #EXEC:Get-Date -Format "yyyy-MM-dd dddd"
proxy  ←  OK:{date} {dow}                    ← #EXEC 等命令完成后直接返回输出

proxy  →  #EXEC:Invoke-RestMethod "https://timor.tech/api/holiday/info/{date}"
proxy  ←  OK:{holiday_json}                  ← AI 从输出中提取节日名称

proxy  →  #EXEC:Write-Output "Summary: Today is {date} ({dow}). {holiday}."
proxy  ←  OK:Summary: ...
```

### 步骤
1. 录制终端启动 TCP server，显示 `TCP server listening on localhost:9999`。
2. AI 发送 `#EXEC:Get-Date -Format "yyyy-MM-dd dddd"`，直接读回输出 `{date} {dow}`。
3. AI 根据读到的 `{date}`，构造并发送 `#EXEC:Invoke-RestMethod "https://timor.tech/api/holiday/info/{date}"`，直接读回节日信息。
4. AI 根据前两步读到的内容，构造并发送 `#EXEC:Write-Output "Summary: Today is {date} ({dow}). {holiday}."`。
5. 演示结束，server 停止。

### 特点
- `#EXEC` 等待命令完成（或超时）后直接返回实际输出，AI 立即可用。
- 不使用任何 shell 变量，日期和节日名称由 AI 从输出中提取后硬编码到后续命令中。
- 画面上能看到每一步的中间输出，过程更直观，体现"AI 在看、在想、在做"。

### 录制要求
- **禁止预编排脚本**：每条 `#EXEC` 必须单独发送、单独读取返回值，根据实际返回内容决定下一条命令。
- 不得用 bash 脚本一次性串联所有命令，否则不算"交互"。

---

## 关键画面（两版共同）
- 终端先显示 server 已启动。
- 屏幕上先出现当天日期与星期。
- 接着出现这一天对应的节日信息。
- 最后出现一条汇总后的自然语言结果。

## 备注
- 这是一个非 TUI demo，重点是"先得到日期，再用这个日期查数据，再汇总输出"。
- 文档里不强调固定日期，因为重点是"先获得日期，再查询对应内容"。
- 节日数据依赖外部 API，复现时需要注意网络。
- 版本 A 展示的是 shell 会话持久化能力；版本 B 展示的是 AI 逐步观察决策能力。
