"""Phase 2 proxy application for the 1.0 protocol core."""

from __future__ import annotations

import argparse
import socket
import sys

HOST = "127.0.0.1"
END_MARKER = "##END##"
BYE_MARKER = "#BYE"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Python mainline proxy")
    parser.add_argument("command", nargs="?", default="")
    parser.add_argument("--port", type=int, default=9999)
    return parser


def read_response(sock: socket.socket) -> str:
    # 响应是有界消息，以 \n##END##\n（或 #BYE）帧尾结束。标记是 ASCII，在字节层查找即可，
    # 无需中途解码；收全后再一次性解码，避免多字节 UTF-8 字符被 recv 边界劈开导致解码崩溃。
    end = END_MARKER.encode("utf-8")
    bye = BYE_MARKER.encode("utf-8")
    chunks: list[bytes] = []
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
        buf = b"".join(chunks)
        if end in buf or bye in buf:
            break
    lines = b"".join(chunks).decode("utf-8", errors="replace").splitlines()
    output: list[str] = []
    for line in lines:
        if line in {END_MARKER, BYE_MARKER}:
            break
        output.append(line)
    return "\n".join(output)


def main() -> int:
    # TUI 快照含 ❯、框线符等非 GBK 字符；Windows 控制台默认 GBK 会让 print 崩。
    # 统一把输出重配成 UTF-8 容错，避免代理打印响应时 UnicodeEncodeError。
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        print("Usage: proxy.py <command> [--port PORT]", file=sys.stderr)
        return 1

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, args.port))
    try:
        sock.sendall((args.command + "\n").encode("utf-8"))
        response = read_response(sock)
    finally:
        sock.close()

    print(response)
    return 0
