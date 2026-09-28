# -*- coding: utf-8 -*-
"""Minimal protocol-compatible fake daemon that runs under CPython 2.7.

Used by ``test/live/registration/registration_py27_tb.py``: registration must
deploy/select ``ramic_bridge_daemon_27.py`` and step 5 needs a daemon that can
answer the token/1+1 smoke without a CIW.  This file intentionally avoids
f-strings and Python-3-only annotations so ``python2.7`` can execute it.
"""
from __future__ import print_function

import argparse
import json
import socket
import sys

STX = b"\x02"
NAK = b"\x15"
RS = b"\x1e"


def _send(conn, marker, payload):
    conn.sendall(marker + json.dumps(payload).encode("utf-8") + RS)


def handle(conn, token):
    try:
        chunks = []
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        request = json.loads(b"".join(chunks).decode("utf-8"))
        if request.get("token") != token:
            _send(conn, NAK, {"error": "invalid token", "log": ""})
            return
        skill = request.get("skill", "")
        if "RBDToken" in skill:
            value = token
        elif "1+1" in skill:
            value = "2"
        elif "boom" in skill:
            _send(conn, NAK, {"error": "boom-error", "log": ""})
            return
        else:
            value = "3"
        _send(conn, STX, {"value": value, "log": ""})
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", args.port))
    sock.listen(64)
    sys.stdout.write("listening 127.0.0.1:%d\n" % args.port)
    sys.stdout.flush()
    while True:
        conn, _addr = sock.accept()
        handle(conn, args.token)


if __name__ == "__main__":
    main()
