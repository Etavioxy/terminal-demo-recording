# terminal-demo-recording

[English](README.md) | 中文

跨平台 AI 驱动的终端演示录制——通过 TCP 透明代理录制 AI 操作，输出 asciinema `.cast` 文件。

## 快速开始

**Windows**：

```powershell
py -3 src/recorder.py --new-window --wait
py -3 src/proxy.py '#ECHO:demo start'
py -3 src/proxy.py '#EXIT'
```

**Linux / macOS**：

```bash
python3 src/recorder.py --wait  # 在另一个终端
python3 src/proxy.py '#ECHO:demo start'
python3 src/proxy.py '#EXIT'
```

## 播放

```bash
cd player && npm install && npm run build && npx vite preview
```

## 依赖

- **Windows**：[PowerSession-rs](https://github.com/nicehash/PowerSession-rs)
- **Linux/macOS**：[asciinema](https://asciinema.org)
- Node.js + npm（player）
- [agg](https://github.com/asciinema/agg)（GIF 导出，可选）

完整的录制流程、TUI 控制命令与 AI 录制指导见 [SKILL.md](SKILL.md)；当前命令速查见 [COMMANDS-CURRENT.md](COMMANDS-CURRENT.md)。

## License

MIT
