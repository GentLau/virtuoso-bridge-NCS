#!/bin/bash
# 在 wsl-gent 上为一个用户准备"启动即完整"的 bridge 实例（以该用户身份执行）。
# 用法（本机）: scp test/shared/runners/bringup_user.sh <user>@wsl-gent:~ && \
#              ssh -o User=<user> wsl-gent 'bash ~/bringup_user.sh <user> <daemon端口>'
# 前置：~/.virtuoso-bridge/<user>/ramic/ 下已有 ramic_bridge_daemon_3.py / _27.py / ramic_bridge.il
# 效果：写出 setup/virtuoso_setup.il + run/.cdsinit + run/cds.lib（来自 ~/project/main），
#       并用 xvfb-run 起 headless Virtuoso（独立 display），daemon 端口 = 参数。
# 用法: bash bringup_user.sh <用户> <daemon端口>
set -eu
USER_NAME=$1
PORT=$2
ROOT="$HOME/.virtuoso-bridge/$USER_NAME"

echo "== 准备目录 $ROOT =="
mkdir -p "$ROOT/ramic" "$ROOT/setup" "$ROOT/run" "$ROOT/status" "$ROOT/tmp"

echo "== run 目录的完整环境（cds.lib + .cdsinit）=="
cp -f "$HOME/project/main/cds.lib" "$ROOT/run/cds.lib"
cat > "$ROOT/run/.cdsinit" <<EOF
load("$ROOT/setup/virtuoso_setup.il")
EOF

echo "== setup 文件 =="
cat > "$ROOT/setup/virtuoso_setup.il" <<EOF
; Generated for $USER_NAME (2026-09-23) — 启动即完整
RBDPath = "$ROOT/ramic/ramic_bridge_daemon_3.py"
RBPython = "python3"
RBPort = $PORT
RBIdentityPath = "$ROOT/status/daemon_identity.txt"
RBDToken = "vb-$USER_NAME"
RBTempDir = "$ROOT"
RBDLogPath = "$ROOT/status/daemon.log"
printf("[RAMIC] token=%L\n" RBDToken)
load("$ROOT/ramic/ramic_bridge.il")
EOF

echo "== 起 Virtuoso（headless X，独立 display）=="
cd "$ROOT/run"
# 进程检测按 **cwd** 匹配：实例的 argv 是 `virtuoso -cdslib ./cds.lib`（相对路径），
# 用 "$ROOT/run/cds.lib" 去 pgrep -f 永远匹配不到 → 会重复拉起。
RUNNING=""
for p in $(pgrep -f "dfII/bin/64bit/virtuoso" || true); do
    if [ "$(readlink "/proc/$p/cwd" 2>/dev/null || true)" = "$ROOT/run" ]; then
        RUNNING=$p
    fi
done
if [ -n "$RUNNING" ]; then
    echo "  已在运行，跳过"
else
    # 上一次会话被挂死/强杀时会留下 CDS.log.cdslck，新实例会直接
    # "Log file Initialization failure" 起不来（P-021 类陈旧锁）。
    rm -f "$ROOT/run/CDS.log.cdslck"
    nohup xvfb-run -a --server-args="-screen 0 1280x1024x24" \
        virtuoso -cdslib ./cds.lib -log ./CDS.log > start.log 2>&1 &
    echo "  launched pid=$!"
fi

echo "== 等待 daemon 监听 $PORT =="
for _ in $(seq 1 60); do
    if ss -ltn | grep -q ":$PORT "; then echo "  LISTENING $PORT"; break; fi
    sleep 2
done
ss -ltn | grep ":$PORT " || echo "  NOT LISTENING (看 $ROOT/run/start.log)"
