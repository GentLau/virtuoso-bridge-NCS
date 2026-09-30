# 日常环境恢复 · lab 四台保活 + labns 服务拉起（Windows 侧入口）
#
# 用途：本机的 w1-gent..w4-gent 是 **WSL distro**；WSL 会把空闲 distro 停掉，
# distro 一停，它的 labns / veth / sshd 全部消失 → Windows 直接表现为
# `ssh wN-gent` Connection timed out（2026-09-30 实际发生）。
#
# 前置：`~/.wslconfig` 的 `[wsl2] firewall=true` **必须保留**（见该文件注释：
# 它决定 VM 落在 172.20.160.0/20，与 lab 身份 IP 172.20.170.2x 同段）。
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File test/shared/runners/lab_keepalive.ps1
# Then (optional) re-create the w1 resident fakes:
#   scp test/shared/runners/start_lab_fakes.sh w1-gent:/tmp/ && ssh w1-gent 'bash /tmp/start_lab_fakes.sh'
# Finally:
#   PYTHONPATH=src python test/shared/runners/resident_env_check.py   # expect remote 8/8
$distros = @('w1-gent', 'w2-gent', 'w3-gent', 'w4-gent')

foreach ($d in $distros) {
    Write-Host "=== keepalive + labns: $d"
    Start-Process -FilePath "wsl.exe" -ArgumentList "-d", $d, "-u", "root", "-e", "sleep", "infinity" -WindowStyle Hidden
    Start-Sleep -Seconds 2
    wsl.exe -d $d -u root -e sh -c 'systemctl start wsl-lab-netns.service wsl-lab-boot.service 2>/dev/null; sleep 3; ip -n labns -4 addr show 2>/dev/null | grep -o "172.20.170.[0-9]*" | head -1' 2>&1 |
        Where-Object { $_ -match '172\.20' } | ForEach-Object { Write-Host "   lab ip: $_" }
}

Start-Sleep -Seconds 3
Write-Host "=== windows-side ssh"
foreach ($h in $distros) {
    $out = ssh -o BatchMode=yes -o ConnectTimeout=10 $h 'hostname' 2>&1
    Write-Host ("   {0} => {1}" -f $h, $out)
}
