"""占住一段本机端口，用来复现"机器级端口被占"这类假红（P-063）。

用法::

    python test/shared/runners/hold_ports.py 65081 65130        # 占满区间，Ctrl-C 释放
    python test/shared/runners/hold_ports.py 65081 65130 --hold 120

背景：`RegistrationFlow.validate()` 在 remote 模式会真实探测/分配 local tunnel 端口
（`register.probe.allocate_local_port(start=65081, tries=50)`）。同机有别的跑测/隧道
占住这个区间时，注册类离线用例会出现**与产品无关的假红**——这个脚本就是用来
确定性地复现/回归那种条件的。
"""
from __future__ import annotations

import argparse
import socket
import time


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("start", type=int)
    parser.add_argument("end", type=int)
    parser.add_argument("--hold", type=float, default=0.0, help="占住多少秒（0=直到 Ctrl-C）")
    args = parser.parse_args(argv)

    held: list[socket.socket] = []
    for port in range(args.start, args.end + 1):
        sock = socket.socket()
        try:
            sock.bind(("127.0.0.1", port))
            sock.listen(1)
            held.append(sock)
        except OSError:
            sock.close()
    print(f"holding {len(held)} ports in [{args.start}, {args.end}]", flush=True)
    try:
        if args.hold:
            time.sleep(args.hold)
        else:
            while True:
                time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        for sock in held:
            sock.close()
    print("released", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
