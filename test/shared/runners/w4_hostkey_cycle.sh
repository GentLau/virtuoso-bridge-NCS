#!/bin/bash
# w4-gent host-key 轮换（注册专项 P5 接口，测试侧维护；需 root/sudo，w4 测试期间独占）
#
# 接口（TB 按这个调）：
#   w4_hostkey_cycle.sh status     # SET=<original|a|b> + FINGERPRINT=SHA256:...
#   w4_hostkey_cycle.sh use-a      # 切到 A 套（= 首次调用时备份的原始 host key）并重启 sshd
#   w4_hostkey_cycle.sh use-b      # 生成/切到 B 套（ed25519/rsa/ecdsa 全新）并重启 sshd
#   w4_hostkey_cycle.sh restore    # 恢复原始 host key 并重启 sshd（TB 需在 finally 调用）
#
# 约束：只用于 w4；产品注册强制目标解析到 22 端口，w4 满足；换 key 会影响客户端
# known_hosts（TB 负责备份/恢复自己的 known_hosts，或用 no-check 调控制命令）。
set -eu

BASE=/var/lib/vb-hostkey-cycle
SSH_DIR=/etc/ssh
ALGS="ed25519 rsa ecdsa"

die() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" = "0" ] || die "run as root (sudo)"

fingerprint() {
    ssh-keygen -lf "$SSH_DIR/ssh_host_$1_key.pub" 2>/dev/null | awk '{print $2}'
}

print_status() {
    local set_name="unknown"
    [ -f "$BASE/current" ] && set_name=$(cat "$BASE/current")
    echo "SET=$set_name"
    echo "FINGERPRINT=$(fingerprint ed25519)"
    echo "RSA_FINGERPRINT=$(fingerprint rsa)"
    echo "ECDSA_FINGERPRINT=$(fingerprint ecdsa)"
}

backup_original() {
    [ -f "$BASE/original/ssh_host_ed25519_key" ] && return 0
    mkdir -p "$BASE/original"
    for alg in $ALGS; do
        cp -a "$SSH_DIR/ssh_host_${alg}_key" "$SSH_DIR/ssh_host_${alg}_key.pub" "$BASE/original/"
    done
    echo "original" > "$BASE/current"
}

make_set_b() {
    [ -f "$BASE/set-b/ssh_host_ed25519_key" ] && return 0
    mkdir -p "$BASE/set-b"
    for alg in $ALGS; do
        ssh-keygen -q -t "$alg" -N "" -f "$BASE/set-b/ssh_host_${alg}_key" >/dev/null
    done
    chmod 600 "$BASE"/set-b/*_key
    chmod 644 "$BASE"/set-b/*_key.pub
}

install_keys() {
    for alg in $ALGS; do
        cp -a "$1/ssh_host_${alg}_key" "$SSH_DIR/ssh_host_${alg}_key"
        cp -a "$1/ssh_host_${alg}_key.pub" "$SSH_DIR/ssh_host_${alg}_key.pub"
        chmod 600 "$SSH_DIR/ssh_host_${alg}_key"
        chmod 644 "$SSH_DIR/ssh_host_${alg}_key.pub"
    done
}

restart_sshd() {
    if systemctl restart ssh 2>/dev/null && systemctl is-active --quiet ssh; then
        return 0
    fi
    if /etc/init.d/ssh restart >/dev/null 2>&1; then
        return 0
    fi
    # 兜底：先装回原始 key，避免把 w4 锁在外面
    install_keys "$BASE/original"
    echo "original" > "$BASE/current"
    die "sshd restart failed; original keys reinstalled"
}

cmd=${1:-status}
case "$cmd" in
    status) print_status ;;
    use-a)
        backup_original
        install_keys "$BASE/original"
        echo "a" > "$BASE/current"
        restart_sshd
        print_status
        ;;
    use-b)
        backup_original
        make_set_b
        install_keys "$BASE/set-b"
        echo "b" > "$BASE/current"
        restart_sshd
        print_status
        ;;
    restore)
        backup_original
        install_keys "$BASE/original"
        echo "original" > "$BASE/current"
        restart_sshd
        print_status
        ;;
    *)
        die "unknown command '$cmd' (status|use-a|use-b|restore)"
        ;;
esac
