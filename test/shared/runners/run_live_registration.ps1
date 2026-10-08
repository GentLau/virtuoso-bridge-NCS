# 真机级 registration/ 全量编排（round10 新增）：六步 / 跨主机 / 真 CIW / py2.7 /
# host-key 轮换 / 控制面（只读 + 写通道），一场景一日志 + 证据。
#
# 用法：
#   powershell -NoProfile -File test/shared/runners/run_live_registration.ps1
#   powershell -NoProfile -File test/shared/runners/run_live_registration.ps1 -Only six_local,py27
param(
    [string]$Out = 'test/artifacts/evidence/round10/registration',
    [string]$Only = ''
)
$ErrorActionPreference = 'Continue'
$env:PYTHONPATH = 'src'
New-Item -ItemType Directory -Force -Path $Out | Out-Null

$cases = @(
    @{ name = 'six_local'; file = 'registration_http_six_step_tb.py';
       args = @('--work-dir', 'test/artifacts/env/reg-six-r10', '--user', 'vbsixr10', '--local-mode') },
    @{ name = 'six_remote_14'; file = 'registration_http_six_step_tb.py';
       args = @('--work-dir', 'test/artifacts/env/reg-six-remote-r10', '--user', 'vbsixrtr10',
                '--daemon-port', '65133', '--root', '/home/Gent/.virtuoso-bridge/vbsixrtr10',
                '--stop-after-deploy') },
    @{ name = 'cov_registration_real'; file = '../../semi/registration/cov_registration_real.py';
       args = @('--work-dir', 'test/artifacts/env/cov-registration', '--user', 'covreg',
                '--token', 'cov-token', '--port', '65112') },
    @{ name = 'role_split'; file = 'registration_role_split_tb.py';
       args = @('--work-dir', 'test/artifacts/env/reg-role-split-r10') },
    @{ name = 'real_ciw'; file = 'registration_real_ciw_tb.py';
       args = @('--work-dir', 'test/artifacts/env/reg-real-ciw-r10') },
    @{ name = 'py27'; file = 'registration_py27_tb.py';
       args = @('--work-dir', 'test/artifacts/env/reg-py27-r10') },
    @{ name = 'hostkey_rotation'; file = 'registration_hostkey_rotation_tb.py';
       args = @('--work-dir', 'test/artifacts/env/reg-hostkey-r10') },
    @{ name = 'control_plane'; file = 'control_plane_tb.py'; args = @() },
    @{ name = 'control_plane_write'; file = 'control_plane_write_tb.py'; args = @() }
)

$picked = $cases | Where-Object { -not $Only -or ($Only -split ',' -contains $_.name) }
$rows = @()
foreach ($case in $picked) {
    $log = Join-Path $Out "$($case.name).log"
    $evidence = Join-Path $Out "$($case.name).json"
    $script = if ($case.file.StartsWith('..')) { "test/semi/registration/" + (Split-Path $case.file -Leaf) }
              else { "test/live/registration/" + $case.file }
    Write-Host "=== $($case.name) ==="
    $started = Get-Date
    & python $script @($case.args) --out $evidence *>&1 | Out-File -Encoding utf8 $log
    $rc = $LASTEXITCODE
    $seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
    Write-Host ("    {0} (rc={1}, {2}s)" -f ($(if ($rc -eq 0) { 'PASS' } else { 'FAIL' })), $rc, $seconds)
    $rows += [pscustomobject]@{ case = $case.name; rc = $rc; seconds = $seconds; log = $log; evidence = $evidence }
}

$summary = [pscustomobject]@{
    generated = (Get-Date).ToString('s')
    all_passed = (@($rows | Where-Object { $_.rc -ne 0 }).Count -eq 0)
    cases = $rows
}
$summary | ConvertTo-Json -Depth 4 | Out-File -Encoding utf8 (Join-Path $Out 'summary.json')
$summary | ConvertTo-Json -Depth 4
if ($summary.all_passed) { exit 0 } else { exit 1 }
