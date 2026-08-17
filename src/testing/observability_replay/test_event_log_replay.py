"""observability + replay 纯单测：事件日志基线字段 + 重放逐条时序驱动。

纯逻辑、注入时钟/发送/sleep，不起 server、不录制、不联网。
event_log 与 replay 经 JSONL 文本格式解耦——本测试同时覆盖"写→读→重放"闭环。
"""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # src

from server.event_log import EventLog  # noqa: E402
from server import app  # noqa: E402  _classify(补回的 kind/生效 timeout 基线字段)
import replay  # noqa: E402


class FakeClock:
    """可控虚拟时钟：按预设时间点依次返回。"""

    def __init__(self, ticks):
        self._ticks = list(ticks)
        self._i = 0

    def __call__(self):
        t = self._ticks[self._i]
        self._i += 1
        return t


# ---------- event_log：可复现性基线字段 ----------

def test_emit_baseline_fields(tmp_path):
    log = EventLog(tmp_path / "e.jsonl", clock=FakeClock([100.0, 100.5, 102.0])).open()
    r1 = log.emit("#EXEC:claude timeout=4000")
    r2 = log.emit("#TYPE:3<C-M>")
    r3 = log.emit("#EXIT")
    log.close()
    # 序号递增
    assert [r["seq"] for r in (r1, r2, r3)] == [1, 2, 3]
    # 首条 rel_ms 为空(无前序)，后续为与上一条的相对毫秒
    assert r1["rel_ms"] is None
    assert r2["rel_ms"] == 500.0
    assert r3["rel_ms"] == 1500.0
    # 原始 wire 串原样保留(隐含类型/输入/timeout)
    assert r1["wire"] == "#EXEC:claude timeout=4000"


def test_emit_optional_diag_fields_and_none_filtered(tmp_path):
    log = EventLog(tmp_path / "e.jsonl", clock=FakeClock([1.0])).open()
    rec = log.emit("#EXEC:claude", pid=1234, exit=None, lock=True)
    log.close()
    assert rec["pid"] == 1234 and rec["lock"] is True
    assert "exit" not in rec  # None 值被过滤


def test_jsonl_file_is_one_event_per_line(tmp_path):
    p = tmp_path / "e.jsonl"
    log = EventLog(p, clock=FakeClock([1.0, 2.0])).open()
    log.emit("#EXEC:a")
    log.emit("#VIEW")
    log.close()
    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["wire"] == "#EXEC:a"


# ---------- replay：读取 + 逐条时序驱动 ----------

def _write_log(tmp_path, ticks, wires):
    log = EventLog(tmp_path / "e.jsonl", clock=FakeClock(ticks)).open()
    for w in wires:
        log.emit(w)
    log.close()
    return tmp_path / "e.jsonl"


def test_load_commands_roundtrip(tmp_path):
    p = _write_log(tmp_path, [10.0, 10.2, 11.0], ["#EXEC:x", "#TYPE:hi", "#EXIT"])
    cmds = replay.load_commands(p)
    assert [w for _, w in cmds] == ["#EXEC:x", "#TYPE:hi", "#EXIT"]
    assert cmds[0][0] == 0.0          # 首条无等待
    assert cmds[1][0] == 200.0        # rel_ms 保留
    assert cmds[2][0] == 800.0


def test_replay_sends_in_order_with_waits(tmp_path):
    p = _write_log(tmp_path, [0.0, 0.05, 0.10], ["#EXEC:x", "#TYPE:hi", "#EXIT"])
    sent, waits = [], []
    replay.replay(p, send=sent.append, sleep=waits.append)
    assert sent == ["#EXEC:x", "#TYPE:hi", "#EXIT"]      # 顺序一致
    # rel_ms 相对上一条：TYPE 相对 EXEC=50ms、EXIT 相对 TYPE=50ms；首条 rel=0 不 sleep
    assert waits == [50.0 / 1000.0, 50.0 / 1000.0]


def test_replay_max_wait_clamps_long_idle(tmp_path):
    p = _write_log(tmp_path, [0.0, 30.0], ["#EXEC:x", "#TYPE:hi"])  # 30s 空档
    waits = []
    replay.replay(p, send=lambda w: None, sleep=waits.append, max_wait_ms=500)
    assert waits == [0.5]  # 30000ms 被钳到 500ms


def test_load_commands_skips_blank_and_no_wire(tmp_path):
    p = tmp_path / "e.jsonl"
    p.write_text('\n{"seq":1,"rel_ms":null}\n{"seq":2,"rel_ms":10,"wire":"#EXIT"}\n', encoding="utf-8")
    cmds = replay.load_commands(p)
    assert [w for _, w in cmds] == ["#EXIT"]  # 空行与无 wire 行被忽略


# ---------- _classify：补回的 kind + 生效 timeout 基线字段 ----------

def test_classify_kind_and_effective_timeout():
    # 显式 timeout 原样记录
    assert app._classify("#EXEC:claude timeout=4000") == ("EXEC", 4000)
    assert app._classify("#TYPE:hi timeout=500") == ("TYPE", 500)
    assert app._classify("#VIEW timeout=800") == ("VIEW", 800)
    # 未给 timeout 时记"生效默认"(与 handle_cmd 同源)
    assert app._classify("#EXEC:claude") == ("EXEC", app.DEFAULT_EXEC_TIMEOUT_MS)
    assert app._classify("#TYPE:hi") == ("TYPE", app.DEFAULT_TYPE_TIMEOUT_MS)
    assert app._classify("#VIEW") == ("VIEW", 0)
    # 无 timeout 语义的命令
    assert app._classify("#ECHO:hey") == ("ECHO", None)
    assert app._classify("#WAITPROC") == ("WAITPROC", None)
    assert app._classify("#EXIT") == ("EXIT", None)


def test_load_commands_ignores_diag_fields_uses_wire_only(tmp_path):
    # 日志含 kind/timeout_ms 观测字段，但重放只取 wire+rel_ms
    p = tmp_path / "e.jsonl"
    p.write_text('{"seq":1,"rel_ms":null,"wire":"#EXEC:x","kind":"EXEC","timeout_ms":30000}\n',
                 encoding="utf-8")
    assert replay.load_commands(p) == [(0.0, "#EXEC:x")]
