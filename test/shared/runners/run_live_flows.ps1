# 真机级 flows/ 全量编排（round10 新增）：逐场景跑 + 一场景一日志/证据。
#
# 为什么需要：flows/ 的 TB 一直是"单独手动跑"，没有编排入口；round10 要求
# "至少两个完整工程 + 多用户/多跳/规模"全部真机复跑并留下本轮证据。
#
# 用法：
#   powershell -NoProfile -File test/shared/runners/run_live_flows.ps1
#   powershell -NoProfile -File test/shared/runners/run_live_flows.ps1 -Only role_split,scale_100
#
# 前置（round10 实测踩过）：
#   * `role_split` 要显式 `--user/--token`（默认 user 与 scenario-role-split 注册表不符）；
#   * `multihop` 需要 w1 上的 hop fake：`scp test/shared/runners/start_hop_fake.sh w1-gent:/tmp/`
#     然后 `ssh w1-gent 'bash /tmp/start_hop_fake.sh'`（端口 65203）；
#   * `s11_full` 不吃 `--out`，用 `--run-dir`。
param(
    [string]$Out = 'test/artifacts/evidence/round10/flows',
    [string]$Only = ''
)
$ErrorActionPreference = 'Continue'
$env:PYTHONPATH = 'src'
New-Item -ItemType Directory -Force -Path $Out | Out-Null

# name -> 参数（--out 由本脚本统一加）
$flows = @(
    @{ name = 'role_split'; file = 'role_split_tb.py';
       args = @('--work-dir', 'test/artifacts/env/scenario-role-split',
                '--user', 'rolesplit', '--token', 'vb-s11') },
    @{ name = 'scale_100';  file = 'scale_100_tb.py';             args = @('--count', '100', '--rounds', '2') },
    @{ name = 'handoff';    file = 'multiuser_layout_handoff_tb.py';
       args = @('--work-dir', 'test/artifacts/env/log-vblog') },
    @{ name = 'multiuser_serdes'; file = 'multiuser_serdes_rx_tb.py'; args = @() },
    @{ name = 'adc_sar';    file = 'adc_sar_flow_tb.py';          args = @() },
    @{ name = 'design_iterate'; file = 'design_iterate_tb.py';    args = @() },
    @{ name = 'serdes_rx';  file = 'serdes_rx_flow_tb.py';        args = @('--with-calibre') },
    @{ name = 'multihop';   file = 'multihop_jump_tb.py';
       args = @('--work-dir', 'test/artifacts/env/multihop') },
    @{ name = 's11_full';   file = 's11_full_flow.py';            args = @('--token', 'vb-s11');
       out_flag = '--run-dir' }
)

$picked = $flows | Where-Object { -not $Only -or ($Only -split ',' -contains $_.name) }
$rows = @()
foreach ($flow in $picked) {
    $log = Join-Path $Out "$($flow.name).log"
    $evidence = Join-Path $Out "$($flow.name).json"
    $outFlag = if ($flow.ContainsKey('out_flag')) { $flow.out_flag } else { '--out' }
    if ($outFlag -eq '--run-dir') { $evidence = Join-Path $Out $flow.name }
    Write-Host "=== $($flow.name) ==="
    $started = Get-Date
    & python ("test/live/flows/" + $flow.file) @($flow.args) $outFlag $evidence *>&1 |
        Out-File -Encoding utf8 $log
    $rc = $LASTEXITCODE
    $seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
    Write-Host ("    {0} (rc={1}, {2}s)" -f ($(if ($rc -eq 0) { 'PASS' } else { 'FAIL' })), $rc, $seconds)
    $rows += [pscustomobject]@{ flow = $flow.name; rc = $rc; seconds = $seconds; log = $log; evidence = $evidence }
}

$summary = [pscustomobject]@{
    generated = (Get-Date).ToString('s')
    all_passed = (@($rows | Where-Object { $_.rc -ne 0 }).Count -eq 0)
    flows = $rows
}
$summary | ConvertTo-Json -Depth 4 | Out-File -Encoding utf8 (Join-Path $Out 'summary.json')
$summary | ConvertTo-Json -Depth 4
if ($summary.all_passed) { exit 0 } else { exit 1 }
