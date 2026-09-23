"""Standalone protocol-accurate fake daemons for a remote host without Virtuoso.

One TCP listener per user (127.0.0.1:<base+n>), one token each.  Speaks the
same wire protocol as the real bottom daemon (STX/NAK + JSON + RS) so the
middle layer exercises its real routing/tunnel/parse path.  Commands and
files still go through the host sshd.

Usage (on vps):
    mkdir -p ~/.virtuoso-bridge/cloud-support/tmp
    nohup python3 fake_daemon_host.py --base-port 6701 --count 10 \
        --token-prefix cloud \
        > ~/.virtuoso-bridge/cloud-support/tmp/fake.log 2>&1 &
"""

from __future__ import annotations

import argparse
import json
import socket
import threading

STX = b"\x02"
NAK = b"\x15"
RS = b"\x1e"


def handle(conn: socket.socket, token: str) -> None:
    try:
        chunks = []
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        req = json.loads(b"".join(chunks).decode("utf-8"))
        if req.get("token") != token:
            conn.sendall(NAK + json.dumps({"error": "invalid token", "log": ""}).encode() + RS)
            return
        skill = req.get("skill", "")
        if "RBDToken" in skill:
            value = token
        elif "1+1" in skill:
            value = "2"
        elif "boom" in skill:
            conn.sendall(NAK + json.dumps({"error": "boom-error", "log": ""}).encode() + RS)
            return
        else:
            value = "3"
        conn.sendall(STX + json.dumps({"value": value, "log": ""}, ensure_ascii=False).encode() + RS)
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except OSError:
            pass


def serve(port: int, token: str) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", port))
    s.listen(128)
    print(f"listening 127.0.0.1:{port} token={token}", flush=True)
    while True:
        try:
            conn, _addr = s.accept()
        except OSError:
            return
        threading.Thread(target=handle, args=(conn, token), daemon=True).start()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-port", type=int, default=6701)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--token-prefix", default="cloud")
    args = parser.parse_args()

    threads = []
    for i in range(args.count):
        token = f"{args.token_prefix}-{i:02d}"
        t = threading.Thread(target=serve, args=(args.base_port + i, token), daemon=True)
        t.start()
        threads.append(t)
    print(f"started {args.count} fake daemons", flush=True)
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
