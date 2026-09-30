"""Disposable CIW 的 daemon 探活（wsl-gent 侧，python3 直连）。

用法：
    python3 daemon_ping.py <port> <token> [skill_expr]
输出（stdout，一行）：
    OK <skill 返回的 value/output>      或   FAIL <错误>

用途：设计侧 TB 在 start/stop/restart 前后快速自证"daemon 是否在听、token 是否对、
SKILL 是否能跑"，不依赖 Windows 侧的隧道。
"""
import json
import socket
import sys


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: daemon_ping.py <port> <token> [skill_expr]")
        return 2
    port = int(sys.argv[1])
    token = sys.argv[2]
    skill = sys.argv[3] if len(sys.argv) > 3 else "1+1"
    try:
        sock = socket.create_connection(("127.0.0.1", port), timeout=15)
    except OSError as exc:
        print(f"FAIL connect: {exc}")
        return 1
    payload = {"skill": skill, "timeout": 30, "token": token}
    try:
        sock.sendall(json.dumps(payload).encode())
        sock.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            data = sock.recv(65536)
            if not data:
                break
            chunks.append(data)
    except OSError as exc:
        print(f"FAIL io: {exc}")
        return 1
    finally:
        sock.close()
    raw = b"".join(chunks)
    # 帧格式：STX(0x02)/NAK(0x15) + JSON + RS(0x1e)
    body = raw.strip(b"\x02\x15\x1e\r\n")
    try:
        parsed = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        print(f"FAIL decode: {raw[:200]!r}")
        return 1
    if "error" in parsed and parsed["error"]:
        print(f"FAIL {parsed['error']}")
        return 1
    print(f"OK {parsed.get('value', parsed)!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
