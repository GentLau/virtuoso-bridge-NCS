#!/bin/bash
# 可丢弃 CIW（注册专项 P4 预设，测试侧维护）
#
# 在 wsl-gent 上以 Virtuoso 用户执行；启动一个 headless 真 Virtuoso（xvfb），
# 并在 CIW 里加载一个"注入用最小 daemon"（bootstrap，token = vb-<name>）。
#
# TB 侧用 ciw_load_setup.py 通过这个 bootstrap 执行
#     progn(RBStop() load("<注册第 4 步生成的 setup>"))
# 把 CIW 换成注册流程生成的真实 daemon —— 等价于"用户把 load(...) 粘进 CIW"，
# 只是用最小 daemon 模拟这步输入。
#
# 用法（在 wsl-gent 上）:
#   bash start_disposable_ciw.sh <name> <bootstrap_port> [display]
# 输出（一行 KEY=VALUE，供调用方解析）:
#   NAME=.. TOKEN=.. PORT=.. ROOT=.. RUN=..
#
# 依赖：~/.virtuoso-bridge/vblog/run/cds.lib（或 VB_CDSLIB）、ramic 资源
#       （默认取 Linux 客户端仓库副本；可用 VB_RESOURCES 覆盖）。
set -eu

NAME=${1:?usage: start_disposable_ciw.sh <name> <bootstrap_port> [display]}
PORT=${2:?usage: start_disposable_ciw.sh <name> <bootstrap_port> [display]}
DISPLAY_NAME=${3:-}

ROOT="$HOME/.virtuoso-bridge/$NAME"
RES="${VB_RESOURCES:-$HOME/project/vblog/tb-sandbox/linux-client/repo/src/bridge/resources}"
VBIN=$(command -v virtuoso || echo /opt/eda/cadence/IC618/tools/dfII/bin/64bit/virtuoso)

mkdir -p "$ROOT/ramic" "$ROOT/setup" "$ROOT/run" "$ROOT/status" "$ROOT/tmp"

# ramic 资源：优先取仓库（与被测代码同版本），退回一个已部署实例
if [ -f "$RES/ramic_bridge.il" ]; then
    cp -f "$RES/ramic_bridge.il" "$RES/ramic_bridge_daemon_3.py" "$RES/ramic_bridge_daemon_27.py" "$ROOT/ramic/"
elif [ -f "$HOME/.virtuoso-bridge/vblog/ramic/ramic_bridge.il" ]; then
    cp -f "$HOME/.virtuoso-bridge/vblog/ramic/"* "$ROOT/ramic/"
else
    echo "NO_RAMIC_RESOURCES: $RES" >&2; exit 1
fi

# run 目录的完整环境（cds.lib 必须真实存在，不能只有 .cdsinit）
CDSLIB="${VB_CDSLIB:-}"
if [ -z "$CDSLIB" ]; then
    for cand in "$HOME/.virtuoso-bridge/vblog/run/cds.lib" "$HOME/project/vblog/cds.lib" \
                "$HOME/project/test/cds.lib" "$HOME/project/main/cds.lib"; do
        [ -f "$cand" ] && { CDSLIB="$cand"; break; }
    done
fi
if [ -z "$CDSLIB" ] || [ ! -f "$CDSLIB" ]; then echo "NO_CDSLIB" >&2; exit 1; fi
cp -f "$CDSLIB" "$ROOT/run/cds.lib"

cat > "$ROOT/setup/virtuoso_setup.il" <<EOF
; 可丢弃 CIW 的注入用 daemon（bootstrap）— 由 start_disposable_ciw.sh 生成
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

# 同一实例已在跑就先停掉（按 cwd 精确匹配，不用会误伤别的实例的 argv 匹配）
for p in $(pgrep -f "dfII/bin/64bit/virtuoso" || true); do
    if [ "$(readlink "/proc/$p/cwd" 2>/dev/null || true)" = "$ROOT/run" ]; then
        kill "$p" 2>/dev/null || true
    fi
done

cd "$ROOT/run"
if [ -n "$DISPLAY_NAME" ]; then
    export DISPLAY="$DISPLAY_NAME"
    nohup "$VBIN" -cdslib ./cds.lib -log ./CDS.log > start.log 2>&1 &
else
    nohup xvfb-run -a --server-args="-screen 0 1280x1024x24" \
        "$VBIN" -cdslib ./cds.lib -log ./CDS.log > start.log 2>&1 &
fi

for _ in $(seq 1 60); do
    if ss -ltn | grep -q ":$PORT "; then
        echo "NAME=$NAME TOKEN=vb-$NAME PORT=$PORT ROOT=$ROOT RUN=$ROOT/run"
        exit 0
    fi
    sleep 2
done
echo "BOOTSTRAP_NOT_LISTENING port=$PORT; see $ROOT/run/start.log" >&2
exit 1
