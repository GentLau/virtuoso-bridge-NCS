#!/bin/bash
# 多跳专项用的第三个 fake daemon：跑在 w1-gent 的 labns 里，端口 65203，token `vb-hopfake`。
# 常驻的两个 lab fake（65201/65202，token vb-lab11/vb-lab12）令牌不同，不能复用——
# 多跳 TB 里 daemon 角色必须用与自己同 token 的 daemon，否则会拿到 "invalid token"。
#
# 用法：ssh w1-gent-mgmt 'bash -s' < test/shared/runners/start_hop_fake.sh
set -u
port=65203
token=vb-hopfake
user=hopfake
home="$HOME/.virtuoso-bridge/$user"
mkdir -p "$home/tmp" "$home/logs"
sudo -n pkill -f "fake_virtuoso[.]py.*--port $port" 2>/dev/null || true
sudo -n pkill -f "ramic_bridge_daemon_3[.]py 0.0.0.0 $port" 2>/dev/null || true
sleep 1
sudo -n ip netns exec labns nohup python3 /opt/fake/virtuoso/fake_virtuoso.py \
    --daemon /opt/fake/virtuoso/ramic_bridge_daemon_3.py \
    --bind 0.0.0.0 --port "$port" --token "$token" \
    --temp-dir "$home/tmp" > "$home/logs/fake.log" 2>&1 < /dev/null &
sleep 3
ss -ltn | grep -E ":$port" || echo "NOT LISTENING"
