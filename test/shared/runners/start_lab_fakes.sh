#!/bin/bash
# 唤醒后重建 w1 上的两个 lab fake 实例（65201/65202）并在 labns 内长期运行。
set -u
for spec in "65201 vb-lab11 vb-lab11" "65202 vb-lab12 vb-lab12"; do
    set -- $spec
    port=$1; token=$2; user=$3
    home="$HOME/.virtuoso-bridge/$user"
    mkdir -p "$home/tmp" "$home/logs"
    sudo -n pkill -f "fake_virtuoso[.]py.*--port $port" 2>/dev/null || true
    sudo -n pkill -f "ramic_bridge_daemon_3[.]py 0.0.0.0 $port" 2>/dev/null || true
    sleep 1
    sudo -n ip netns exec labns nohup python3 /opt/fake/virtuoso/fake_virtuoso.py \
        --daemon /opt/fake/virtuoso/ramic_bridge_daemon_3.py \
        --bind 0.0.0.0 --port "$port" --token "$token" \
        --temp-dir "$home/tmp" > "$home/logs/fake.log" 2>&1 < /dev/null &
    echo "started $user on $port"
done
sleep 3
ss -ltn | grep -E ":6520[12]" || echo "NOT LISTENING"
