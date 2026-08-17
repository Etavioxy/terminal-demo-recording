"""会话事件日志：把每条进来的协议命令按时序写入 event.jsonl（JSONL，一行一事件）。

可观测性 + 可复现性合一，且互不耦合于 server 内部：
- 可复现性基线(始终记)：seq(顺序号)、ts(绝对时间)、rel_ms(与上一条的相对时序)、wire(原始命令串)。
  记原始 wire 串(如 "#EXEC:claude timeout=4000")即隐含了命令类型/原始输入/生效 timeout——
  重放时逐条按 rel_ms 等待后原样重发即可"基本稳定复现"，无需解析成字段。
- 观测性增强(可选)：emit 的 **extra 字段(如 pid/exit/lock/snapshot_hash)按需附加。

设计要点(模块解耦)：
- 不依赖 server 任何状态；server 只持有一个 EventLog 实例并调 emit()。
- 时钟注入(clock)，生产用 time.time、测试用虚拟时钟，便于纯单测。
- JSONL 文本格式是与 replay 模块之间的唯一接口，双方都不 import 对方。
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path


class EventLog:
    def __init__(self, path, clock=time.time):
        self._path = path
        self._clock = clock
        self._seq = 0
        self._last_ts = None
        self._lock = threading.Lock()
        self._fh = None

    def open(self):
        """打开日志文件并截断(每次 server 启动 = 一次会话 = 一份干净日志)。返回 self 便于链式。

        一个 server 进程对应一次录制会话，故截断写；要保留历史请在下次启动前另存该文件。
        """
        p = Path(self._path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self._fh = p.open("w", encoding="utf-8")
        return self

    def close(self):
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def emit(self, wire, **extra):
        """记录一条进来的命令。wire 为原始命令串；extra 为可选观测字段(None 值忽略)。

        返回写入的记录 dict(便于测试断言)。线程安全。
        """
        with self._lock:
            now = self._clock()
            self._seq += 1
            rel_ms = None if self._last_ts is None else round((now - self._last_ts) * 1000, 1)
            self._last_ts = now
            rec = {"seq": self._seq, "ts": round(now, 4), "rel_ms": rel_ms, "wire": wire}
            rec.update({k: v for k, v in extra.items() if v is not None})
            if self._fh is not None:
                self._fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                self._fh.flush()
            return rec
