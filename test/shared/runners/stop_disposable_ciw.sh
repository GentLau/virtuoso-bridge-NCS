#!/bin/bash
# 停掉 start_disposable_ciw.sh 起的可丢弃 CIW（测试侧维护）。
# 顺序：① 尽力 RBStop（直连本机 daemon 端口）→ ② 按 cwd 杀 Virtuoso →
#       ③ 清掉仍挂在实例根下的 daemon 子进程 → ④ 报端口是否释放。
# 用法（在 wsl-gent 上）: bash stop_disposable_ciw.sh <name> <daemon_port> <token>
set -eu
NAME=${1:?usage: stop_disposable_ciw.sh <name> <daemon_port> <token>}
PORT=${2:?usage: stop_disposable_ciw.sh <name> <daemon_port> <token>}
TOKEN=${3:?usage: stop_disposable_ciw.sh <name> <daemon_port> <token>}
ROOT="$HOME/.virtuoso-bridge/$NAME"

python3 - "$PORT" "$TOKEN" <<'PY' || true
import json, socket, sys
port, token = int(sys.argv[1]), sys.argv[2]
try:
    s = socket.create_connection(("127.0.0.1", port), timeout=10)
    s.sendall(json.dumps({"skill": "RBStop()", "timeout": 8, "token": token,
                          "log_level": "all", "log_max_bytes": 65536}).encode())
    s.shutdown(socket.SHUT_WR)
    while s.recv(65536):
        pass
except OSError:
    pass
PY

for p in $(pgrep -f "dfII/bin/64bit/virtuoso" || true); do
    if [ "$(readlink "/proc/$p/cwd" 2>/dev/null || true)" = "$ROOT/run" ]; then
        kill "$p" 2>/dev/null || true
    fi
done
sleep 1
for p in $(pgrep -f "$ROOT" || true); do kill "$p" 2>/dev/null || true; done

if ss -ltn | grep -q ":$PORT "; then
    echo "STILL_LISTENING port=$PORT"
else
    echo "STOPPED name=$NAME port=$PORT"
fi
