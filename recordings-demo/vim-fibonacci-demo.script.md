# vim-fibonacci-demo

## 主题
展示 AI 不只是执行命令，还能通过 TCP 代理控制 Vim，在终端里逐字写出一个 Python 斐波那契脚本，保存退出，再运行并验证结果。

## 步骤
1. 录制终端启动 TCP server。
2. 先输出开场说明，告诉观众这是一个 AI 控制 Vim 的 TUI 演示。
3. 清屏后进入 Step 1，启动 `vim fib.py`。
4. AI 在 Vim 里逐字输入 Python 代码，内容是一个 `fib(n)` 函数，以及打印前 10 项结果的循环。
5. AI 退出插入模式，输入 `:wq`，保存并退出 Vim。
6. 清屏后进入 Step 2，读取 `fib.py`，让观众看到刚刚写出来的脚本内容。
7. 再清屏进入 Step 3，运行 `py fib.py`。
8. 终端打印 `fib(0)` 到 `fib(9)` 的结果，最后确认前 10 项全部正确。
9. 最后给出总结，说明这次演示依次用到了 `#EXEC`、`#TYPE` 两种协议能力。
10. 演示结束，server 停止。

## 关键画面
- 开场标题：`AI TUI 演示: 在 Vim 中编写斐波那契脚本`
- Vim 打开 `"fib.py" [New File]`
- 逐字输入的代码过程
- 保存退出后的提示：`"fib.py" [New File][unix format] 10 lines, 179 bytes written`
- `Get-Content .\\fib.py` 展示完整脚本
- 运行结果里出现：`fib(9) = 34`
- 总结里明确点出：`#EXEC + #TYPE`

## 备注
- 这是核心 TUI demo，重点不是代码本身，而是“AI 通过终端交互完成编辑、保存、执行”。
- 从 cast 看，这个演示明显比 date-holiday 更像 1.0 的主验收样例。
- 复现时最重要的是保证 Vim 输入、保存退出、以及最终运行结果三段都稳定出现。
