# Run every upper-layer package TB against the real business API and record evidence.
#
#   powershell -NoProfile -File test/shared/runners/run_package_e2e.ps1
#   powershell -NoProfile -File test/shared/runners/run_package_e2e.ps1 -Only schematic,layout
#
# Prerequisites: the business API server is up on 127.0.0.1:8127 with the
# scenario work-dir whose registry holds the token the TBs use (vb-vblog).
#
# Evidence: <OutDir>/<tb>.log (raw stdout+stderr) + <OutDir>/summary.json.
# Exit code is non-zero when any TB reports a FAIL line or exits non-zero, so a
# red TB can never look green in an aggregated report.
param(
    [string]$OutDir = "",
    [string]$Transport = "http",
    [string[]]$Only = @(),
    [string[]]$Skip = @()
)

$ErrorActionPreference = 'Stop'
# test/shared/runners/ 距仓库根 3 层（2026-09-23 两次搬迁：test/tb/runners → test/runners → test/shared/runners）
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
if (-not $OutDir) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $OutDir = Join-Path $Root "test\artifacts\package-e2e-$stamp"
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$all = @('schematic', 'symbol', 'layout', 'cellview', 'verilog', 'veriloga',
         'skillref', 'infra', 'maestro', 'spectre')
if ($Only.Count -gt 0) { $all = $all | Where-Object { $Only -contains $_ } }
if ($Skip.Count -gt 0) { $all = $all | Where-Object { $Skip -notcontains $_ } }

$rows = @()
$failed = 0
foreach ($tb in $all) {
    $scriptPath = Join-Path $Root "test\live\packages\${tb}_e2e_tests.py"
    $logPath = Join-Path $OutDir "$tb.log"
    Write-Host "===== $tb ====="
    $started = Get-Date
    $output = & python $scriptPath --transport $Transport 2>&1
    $exit = $LASTEXITCODE
    $output | Tee-Object -FilePath $logPath
    $text = ($output | Out-String)
    $passes = ([regex]::Matches($text, '(?m)^PASS\b')).Count
    $fails = ([regex]::Matches($text, '(?m)^FAIL\b')).Count
    $seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
    if ($exit -ne 0 -or $fails -gt 0) { $failed++ }
    $rows += [pscustomobject]@{
        tb        = $tb
        exit      = $exit
        passes    = $passes
        fails     = $fails
        seconds   = $seconds
        log       = $logPath.Replace($Root + '\', '')
        ok        = (($exit -eq 0) -and ($fails -eq 0))
    }
}

$stamp = Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz'
$summary = [pscustomobject]@{
    generated_at = $stamp
    transport    = $Transport
    out_dir      = $OutDir.Replace($Root + '\', '')
    total_tbs    = $rows.Count
    total_passes = ($rows | Measure-Object -Property passes -Sum).Sum
    total_fails  = ($rows | Measure-Object -Property fails -Sum).Sum
    failed_tbs   = $failed
    rows         = $rows
}
$summary | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $OutDir 'summary.json') -Encoding UTF8
$rows | Format-Table -AutoSize
Write-Host "passes=$($summary.total_passes) fails=$($summary.total_fails) failed_tbs=$failed"
Write-Host "evidence -> $OutDir"
if ($failed -gt 0) { exit 1 }
