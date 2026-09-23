# 主覆盖率 runner：离线三层 + 离线 TB + 上层包(direct) + 真机 TB + S11 流程
# 复算：powershell -NoProfile -File test/shared/runners/run_main_coverage.ps1
#
# 特点：
#  * 使用**隔离的 COVERAGE_FILE**（test/artifacts/evidence/cov-main/.coverage），
#    避免与其它并行 coverage 进程互相覆盖（2026-09-22 踩过：并行 run 把数据清空）；
#  * 单个步骤失败不中止，最后汇总失败项（便于排查环境类抖动）；
#  * 产出 text/json/branch 三份报告，供"防驳回"口径引用。
$ErrorActionPreference = 'Continue'
# test/shared/runners/ 距仓库根 3 层（2026-09-23 两次搬迁：test/tb/runners → test/runners → test/shared/runners）
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
Set-Location $root

$covDir = Join-Path $root 'test/artifacts/evidence/cov-main'
New-Item -ItemType Directory -Force -Path $covDir | Out-Null
$env:COVERAGE_FILE = Join-Path $covDir '.coverage'

# Admin endpoints are protected by the built-in admin token.  Its plaintext
# must never be committed (the server stores only the SHA-256); it lives in a
# gitignored artifacts file.  Load it when present so the admin paths stay
# covered; otherwise those tests skip with an explicit reason.
$adminTokenFile = 'test/artifacts/admin-token.txt'
if (-not $env:VB_ADMIN_TOKEN -and (Test-Path $adminTokenFile)) {
    $env:VB_ADMIN_TOKEN = (Get-Content $adminTokenFile -Raw).Trim()
    Write-Host '[auth] VB_ADMIN_TOKEN loaded from gitignored file'
}

# Reproducibility metadata: the numbers only mean something together with the
# revision and dirty state they were produced from.
$head = (git rev-parse HEAD).Trim()
$statusLines = @(git status --porcelain)
$diffSha = (git diff HEAD 2>$null | git hash-object --stdin).Trim()
$meta = [ordered]@{
    head              = $head
    branch            = (git branch --show-current).Trim()
    worktree_diff_sha = $diffSha
    dirty             = ($statusLines.Count -gt 0)
    started_utc       = (Get-Date).ToUniversalTime().ToString('o')
    python            = (python -c "import sys;print(sys.version.split()[0])").Trim()
    coverage          = (python -m coverage --version).Trim()
    coverage_file     = $env:COVERAGE_FILE
}
# 注意：Windows PowerShell 5.1 的 `Out-File -Encoding utf8` 会写 BOM，
# 下游用严格 JSON 解析会失败（2026-09-22 实测）。统一用无 BOM 的 UTF-8 写。
[System.IO.File]::WriteAllText(
    (Join-Path $covDir 'run-meta.json'),
    ($meta | ConvertTo-Json -Depth 3),
    (New-Object System.Text.UTF8Encoding($false))
)
Write-Host "[meta] head=$head dirty=$($meta.dirty) diff=$diffSha"

$failures = @()
function Step([string]$name, [scriptblock]$body) {
    Write-Host "== $name" -ForegroundColor Cyan
    try { & $body; if ($LASTEXITCODE -ne 0) { $script:failures += "$name (rc=$LASTEXITCODE)" } }
    catch { $script:failures += "$name ($($_.Exception.Message))" }
}

Step 'erase' { python -m coverage erase }
# 不吞 pytest 输出：离线层一旦红，日志里必须能看到失败用例（2026-09-23 踩过：
# 该步 rc=1 但输出被 Out-Null 吃掉，只能靠重跑才定位）。
Step 'offline L0-L2' { python -m coverage run --branch --source=src -m pytest -p no:cacheprovider test/offline/unit test/offline/integration test/offline/scenario }
Step 'offline/core api-server' { python -m coverage run --branch --append --source=src test/offline/core/api_server_tb.py --out test/artifacts/evidence/api-server.json | Out-Null }
Step 'offline/core semantics' { python -m coverage run --branch --append --source=src test/offline/core/semantics_tb.py --out test/artifacts/evidence/semantics-green.json | Out-Null }
Step 'offline/core fault-injection' { python -m coverage run --branch --append --source=src test/offline/core/fault_injection_tb.py --out test/artifacts/evidence/fault-injection-green.json | Out-Null }
Step 'offline/core daemon-log-protocol' { python -m coverage run --branch --append --source=src test/offline/core/daemon_log_protocol_tb.py --out test/artifacts/evidence/log-protocol.json | Out-Null }

foreach ($suite in 'infra','cellview','schematic','symbol','layout','verilog','veriloga','skillref','spectre','maestro') {
    Step "packages/$suite (direct)" { python -m coverage run --branch --append --source=src "test/live/packages/${suite}_e2e_tests.py" --transport direct | Out-Null }
}

Step 'transport cov_remote_real' { python -m coverage run --branch --append --source=src test/live/transport/cov_remote_real.py --work-dir test/artifacts/env/log-vblog --token vb-vblog | Out-Null }
Step 'transport one_shot_burst' { python -m coverage run --branch --append --source=src test/semi/transport/one_shot_burst_tb.py --work-dir test/artifacts/env/one-shot-burst --token vb-vblog --out test/artifacts/evidence/one-shot-burst-green.json | Out-Null }
Step 'registration six-step (local)' { python -m coverage run --branch --append --source=src test/live/registration/registration_http_six_step_tb.py --work-dir test/artifacts/env/reg-six-local --user vbsixlocal --local-mode --token vb-six-local --out test/artifacts/env/reg-six-local/evidence.json | Out-Null }
Step 'registration 1-4 (remote)' { python -m coverage run --branch --append --source=src test/semi/registration/cov_registration_real.py --work-dir test/artifacts/env/cov-registration --user covreg --token cov-token --port 65112 | Out-Null }
Step 'S11 full flow (LVS)' { python -m coverage run --branch --append --source=src test/live/flows/s11_full_flow.py --work-dir test/artifacts/env/s11 --token vb-s11 --lib CMP_LIB --cell cmp_top --out test/artifacts/env/s11/flow.json | Out-Null }

# ---- evidence reports -------------------------------------------------------------
# Two report thresholds over the same data file:
#   * default config  -> project honouring its own "# pragma: no cover" markers;
#   * strict config   -> pragmas ignored, so no executable line hides behind one.
# Coverage exclusions are applied at *report* time, so both come from one run.
Step 'coverage text (default)' { python -m coverage report -m | Out-File -Encoding utf8 test/artifacts/evidence/cov-main/coverage-main.txt }
Step 'coverage json (default)' { python -m coverage json -o test/artifacts/evidence/cov-main/coverage-main.json }
Step 'coverage text (strict)' { python -m coverage report --rcfile=test/shared/runners/coverage-strict.ini -m | Out-File -Encoding utf8 test/artifacts/evidence/cov-main/coverage-main-strict.txt }
Step 'coverage json (strict)' { python -m coverage json --rcfile=test/shared/runners/coverage-strict.ini -o test/artifacts/evidence/cov-main/coverage-main-strict.json }

New-Item -ItemType Directory -Force -Path test/reports/coverage-pack | Out-Null
Step 'classify uncovered (AST proof)' {
    python test/shared/runners/classify_uncovered.py `
        --json test/artifacts/evidence/cov-main/coverage-main-strict.json `
        --out test/reports/coverage-pack/coverage-rules-auto.json `
        --unclassified-out test/reports/coverage-pack/unclassified.txt | Out-Null
}
Step 'evidence pack (modules + per-line)' {
    python test/shared/runners/coverage_evidence.py `
        --json test/artifacts/evidence/cov-main/coverage-main-strict.json `
        --out-dir test/reports/coverage-pack `
        --rules test/reports/coverage-pack/coverage-rules-auto.json `
        --source-root src
}

Write-Host "`n== 汇总 ==" -ForegroundColor Yellow
Write-Host "COVERAGE_FILE=$env:COVERAGE_FILE"
if ($failures.Count) { Write-Host "失败步骤:"; $failures | ForEach-Object { Write-Host "  - $_" } }
else { Write-Host "全部步骤通过" }
python -m coverage report | Select-Object -Last 2
