# terminal-demo-recording

English | [中文](README.zh.md)

Cross-platform AI-driven terminal demo recording — records AI operations via TCP transparent proxy, outputs asciinema `.cast` files.

## Quick start

**Windows**:

```powershell
py -3 src/recorder.py --new-window --wait
py -3 src/proxy.py '#ECHO:demo start'
py -3 src/proxy.py '#EXIT'
```

**Linux / macOS**:

```bash
python3 src/recorder.py --wait  # in another terminal
python3 src/proxy.py '#ECHO:demo start'
python3 src/proxy.py '#EXIT'
```

## Play

```bash
cd player && npm install && npm run build && npx vite preview
```

## Dependencies

- **Windows**: [PowerSession-rs](https://github.com/nicehash/PowerSession-rs)
- **Linux/macOS**: [asciinema](https://asciinema.org)
- Node.js + npm (player)
- [agg](https://github.com/asciinema/agg) (GIF export, optional)

For the full recording workflow, TUI control commands, and AI recording guidance, see [SKILL.md](SKILL.md). For the current command reference, see [COMMANDS-CURRENT.md](COMMANDS-CURRENT.md).

## License

MIT
