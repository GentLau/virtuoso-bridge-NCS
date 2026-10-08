#!/bin/bash
# bringup_instance.sh —— 在 wsl-gent 上以当前账号启动一个独立 bridge 实例（测试侧维护）
#
# 与 bringup_user.sh 的差异：
#   * 实例名与账号解耦：root=~/.virtuoso-bridge/<name>，token=vb-<name>
#   * 显示号必须显式给定（不再用 xvfb-run -a 的随机 display）
#   * 每个实例一个目录、一份 cds.lib 拷贝、一份 CDS.log（互不共享）
#
# 用法（在目标账号下执行）:
#   bash bringup_instance.sh <name> <daemon_port> <display> [cdslib_src] [ramic_src]
# 例:
#   bash bringup_instance.sh vbuser1b 65411 :112
#   bash bringup_instance.sh vbuser3  65403 :114 /project/main/cds.lib /project/bridge-resources
#
# 默认值:
#   cdslib_src = ~/project/main/cds.lib
#   ramic_src  = ~/.virtuoso-bridge/<当前账号>/ramic（该账号主实例的资源），
#                不存在时退回 /project/bridge-resources
set -eu

NAME=${1:?usage: bringup_instance.sh <name> <port> <display> [cdslib_src] [ramic_src]}
PORT=${2:?usage: bringup_instance.sh <name> <port> <display> [cdslib_src] [ramic_src]}
DISP=${3:?usage: bringup_instance.sh <name> <port> <display> [cdslib_src] [ramic_src]}
CDSLIB_SRC=${4:-$HOME/project/main/cds.lib}
RAMIC_SRC=${5:-$HOME/.virtuoso-bridge/$(whoami)/ramic}
if [ ! -f "$RAMIC_SRC/ramic_bridge.il" ]; then
    RAMIC_SRC=/project/bridge-resources
fi

ROOT="$HOME/.virtuoso-bridge/$NAME"

if [ ! -f "$CDSLIB_SRC" ]; then
    echo "NO_CDSLIB: $CDSLIB_SRC" >&2
    exit 1
fi
if [ ! -f "$RAMIC_SRC/ramic_bridge.il" ]; then
    echo "NO_RAMIC: $RAMIC_SRC" >&2
    exit 1
fi

mkdir -p "$ROOT/ramic" "$ROOT/setup" "$ROOT/run" "$ROOT/status" "$ROOT/tmp"

echo "== 实例资源（每个实例独立副本；ramic 源=$RAMIC_SRC）=="
cp -f "$RAMIC_SRC/ramic_bridge.il" "$ROOT/ramic/"
cp -f "$RAMIC_SRC/ramic_bridge_daemon_3.py" "$ROOT/ramic/"
if [ -f "$RAMIC_SRC/ramic_bridge_daemon_27.py" ]; then
    cp -f "$RAMIC_SRC/ramic_bridge_daemon_27.py" "$ROOT/ramic/"
fi
cp -f "$CDSLIB_SRC" "$ROOT/run/cds.lib"

cat > "$ROOT/setup/virtuoso_setup.il" <<EOF
; Generated for $NAME by bringup_instance.sh ($(date -u +%F))
RBDPath = "$ROOT/ramic/ramic_bridge_daemon_3.py"
RBPython = "python3"
RBPort = $PORT
RBIdentityPath = "$ROOT/status/daemon_identity.txt"
RBDToken = "vb-$NAME"
RBTempDir = "$ROOT"
RBDLogPath = "$ROOT/status/daemon.log"
printf("[RAMIC] token=%L\n" RBDToken)
load("$ROOT/ramic/ramic_bridge.il")
EOF

cat > "$ROOT/run/.cdsinit" <<EOF
load("$ROOT/setup/virtuoso_setup.il")
EOF

echo "== Xvfb $DISP =="
if ! pgrep -f "Xvfb $DISP" >/dev/null 2>&1; then
    nohup Xvfb "$DISP" -screen 0 1280x1024x24 -nolisten tcp \
        > "$ROOT/status/xvfb.log" 2>&1 &
    XSOCK="/tmp/.X11-unix/X${DISP#:}"
    for _ in $(seq 1 30); do
        if [ -S "$XSOCK" ]; then
            break
        fi
        sleep 0.5
    done
    echo "  started on $DISP"
else
    echo "  Xvfb $DISP 已在运行，复用"
fi

echo "== 停掉本实例旧进程（CIW 按 cwd；daemon 按 argv 归属本 root）=="
for p in $(pgrep -f "dfII/bin/64bit/virtuoso" || true); do
    if [ "$(readlink "/proc/$p/cwd" 2>/dev/null || true)" = "$ROOT/run" ]; then
        echo "  kill old CIW pid=$p"
        kill "$p" 2>/dev/null || true
    fi
done
# 杀 CIW 后 IPC 机制会连带清理 daemon（实测 ~0.2–1.2s），但存在 teardown 窗口；
# 这里按 root/端口精确清理并等端口释放，保证重跑同端口时新 daemon 一定能绑上。
for p in $(pgrep -f "ramic_bridge_daemon.*$ROOT" || true); do
    echo "  kill old daemon pid=$p"
    kill "$p" 2>/dev/null || true
done
for _ in $(seq 1 20); do
    if ! ss -ltn | grep -q ":$PORT "; then
        break
    fi
    sleep 1
done
if ss -ltn | grep -q ":$PORT "; then
    echo "  WARN: port $PORT 仍被占用（继续尝试启动）"
fi

rm -f "$ROOT/run/CDS.log.cdslck"
cd "$ROOT/run"
echo "== 启动 Virtuoso (cwd=$ROOT/run, DISPLAY=$DISP) =="
DISPLAY="$DISP" nohup virtuoso -cdslib ./cds.lib -log ./CDS.log > start.log 2>&1 &
echo "  launched pid=$!"

for _ in $(seq 1 90); do
    if ss -ltn | grep -q ":$PORT "; then
        echo "OK NAME=$NAME TOKEN=vb-$NAME PORT=$PORT DISPLAY=$DISP ROOT=$ROOT"
        exit 0
    fi
    sleep 2
done
echo "NOT_LISTENING port=$PORT — tail $ROOT/run/start.log" >&2
tail -20 "$ROOT/run/start.log" >&2 || true
exit 1
