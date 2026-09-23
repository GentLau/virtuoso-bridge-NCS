# Combined coverage + acceptance gate for the current tree.
#
# Every step is fail-fast: a red TB aborts the run instead of producing a
# green-looking coverage report.
#
#   powershell -NoProfile -File test/shared/runners/run_coverage.ps1                     # local+WSL real daemons
#   powershell -NoProfile -File test/shared/runners/run_coverage.ps1 -IncludeExtended    # + WSL client + saturation
#
# Prerequisites
#   * ssh alias ``wsl-gent`` (real Virtuoso with the vb11 + vblog daemons)
#   * registries under test/artifacts/
#   * for -IncludeExtended: WSL sandbox venv at $WslPython with paramiko installed
param(
    [switch]$IncludeExtended = $false,
    [string]$WslHost = 'wsl-gent',
    [int]$FailUnder = 80,
    # Statement-coverage threshold (percent).  Branch coverage is reported
    # separately and only gated when -BranchFailUnder > 0.
    [int]$BranchFailUnder = 0,
    [string]$WslSandbox = '/home/Gent/project/vblog/tb-sandbox',
    [string]$WslPython = '/home/Gent/project/vblog/tb-sandbox/venv/bin/python',
    # Upper-layer package TBs (schematic…spectre) carry most of the
    # pyapi.packages coverage but cost ~8 minutes; skip them only for a smoke run.
    [switch]$SkipPackages = $false,
    # Escape hatch for a shared workspace only: temporary WIP files that do not
    # collect yet.  A submission run MUST NOT pass this parameter.
    [string[]]$SkipTests = @(),
    # Steps whose *environment* is not available (dead daemon, missing token),
    # as a ';'-separated list of label substrings.  ``powershell -File`` cannot
    # pass a PowerShell array, hence the string.  Skipped steps are recorded in
    # coverage-run-skipped.json so a reader can see exactly which evidence a
    # number does and does not include.  A submission run MUST NOT pass it.
    [string]$Skip = '',
    # Coverage data file for this run only (see COVERAGE_FILE below).
    [string]$DataFile = 'test/artifacts/tmp/coverage-db/.coverage-gate'
)

$ErrorActionPreference = 'Stop'
# Native (python/pytest) non-zero exits must abort, otherwise a red TB would
# still produce a green-looking coverage report.
$PSNativeCommandUseErrorActionPreference = $true
$env:PYTHONPATH = 'src'

# Dedicated data file.  The default ``.coverage`` is shared with every other
# coverage user in the workspace: two writers with different ``--branch``
# settings interleave and the file ends up half statement / half branch, after
# which ``coverage report`` refuses to run ("Can't combine statement coverage
# data with branch data") and *no* number can be produced.  COVERAGE_FILE is
# inherited by every ``coverage`` child process below.
$env:COVERAGE_FILE = $DataFile

# Admin endpoints need the built-in admin token; the plaintext lives only in
# the gitignored artifacts file (never in the repo).  Load it when present so
# the admin paths stay covered; otherwise the admin tests skip explicitly.
$adminTokenFile = 'test/artifacts/admin-token.txt'
if (-not $env:VB_ADMIN_TOKEN -and (Test-Path $adminTokenFile)) {
    $env:VB_ADMIN_TOKEN = (Get-Content $adminTokenFile -Raw).Trim()
    Write-Host '[auth] VB_ADMIN_TOKEN loaded from gitignored file'
}

# Steps to skip (environment not available); see the -Skip parameter comment.
$script:skipSteps = @($Skip -split ';' | Where-Object { $_ -ne '' })
$script:skippedSteps = @()

# ---- reproducibility metadata -----------------------------------------------------
# The coverage numbers are only meaningful together with the exact revision and
# the dirty state they were produced from.  ``worktree_diff_sha`` differs from
# ``head`` whenever tracked files are modified.
$evidenceDir = 'test/artifacts'

# ``git`` writes benign warnings to stderr (e.g. the CRLF notice on a Windows
# checkout); with $PSNativeCommandUseErrorActionPreference = $true those abort the
# whole gate before a single test runs.  Capture git output through python so
# stderr never reaches PowerShell's native-command error handling.
function Get-GitText {
    param([string[]]$GitArgs)
    $quoted = ($GitArgs | ForEach-Object { "'" + ($_ -replace "'", "''") + "'" }) -join ', '
    $code = "import subprocess,sys;sys.stdout.write(subprocess.run(['git',$quoted],capture_output=True,text=True).stdout)"
    return (python -c $code)
}

$head = (Get-GitText @('rev-parse', 'HEAD')).Trim()
$statusLines = @(Get-GitText @('status', '--porcelain') -split "`n" | Where-Object { $_ -ne '' })
$diffSha = (python -c "import subprocess,hashlib;d=subprocess.run(['git','diff','HEAD'],capture_output=True).stdout;print(hashlib.sha256(d).hexdigest())").Trim()
$runMeta = [ordered]@{
    head                = $head
    branch              = (Get-GitText @('branch', '--show-current')).Trim()
    worktree_diff_sha   = $diffSha
    dirty               = ($statusLines.Count -gt 0)
    dirty_paths         = $statusLines
    started_utc         = (Get-Date).ToUniversalTime().ToString('o')
    include_extended    = [bool]$IncludeExtended
    fail_under          = $FailUnder
    skip_steps          = $script:skipSteps
    skip_tests          = $SkipTests
    data_file           = $DataFile
    python              = (python -c "import sys;print(sys.version.split()[0])").Trim()
    coverage            = (python -m coverage --version).Trim()
}
$runMeta | ConvertTo-Json -Depth 4 | Out-File -Encoding utf8 "$evidenceDir/coverage-run-meta.json"
Write-Host "[meta] head=$head dirty=$($runMeta.dirty) diff=$diffSha"

function Invoke-Step {
    param([string]$Label, [scriptblock]$Command)
    foreach ($pattern in $script:skipSteps) {
        if ($Label -like "*$pattern*") {
            Write-Host "[skip] $Label (matched -SkipSteps '$pattern')"
            $script:skippedSteps += $Label
            return
        }
    }
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "acceptance step failed: $Label (exit $LASTEXITCODE)"
    }
}


# ---- offline suites and TBs ------------------------------------------------------
Invoke-Step 'coverage erase' { python -m coverage erase }
$ignoreArgs = @()
foreach ($path in $SkipTests) { $ignoreArgs += "--ignore=$path" }
# No ``| Out-Null`` on the steps that can fail for a *test* reason: swallowing
# pytest/TB output leaves a red gate with no diagnosis in the log.
Invoke-Step 'offline suites' { python -m coverage run --branch --source=src -m pytest test/offline/unit test/offline/integration test/offline/scenario -q @ignoreArgs }
Invoke-Step 'fault injection TB' { python -m coverage run --branch --source=src --append test/offline/core/fault_injection_tb.py --out test/artifacts/evidence/fault-injection-green.json | Out-Null }
Invoke-Step 'semantics TB' { python -m coverage run --branch --source=src --append test/offline/core/semantics_tb.py --out test/artifacts/evidence/semantics-green.json | Out-Null }
Invoke-Step 'daemon log protocol TB' { python -m coverage run --branch --source=src --append test/offline/core/daemon_log_protocol_tb.py --out test/artifacts/evidence/log-protocol.json | Out-Null }
Invoke-Step 'top layer HTTP TB' { python -m coverage run --branch --source=src --append test/offline/core/api_server_tb.py --out test/artifacts/evidence/api-server.json | Out-Null }

# ---- registration over the real HTTP API ----------------------------------------
Invoke-Step 'registration 1-6 (local)' { python -m coverage run --branch --source=src --append test/live/registration/registration_http_six_step_tb.py --work-dir test/artifacts/env/reg-six-local --user vbsixlocal --local-mode --token vb-six-local --out test/artifacts/env/reg-six-local/evidence.json | Out-Null }
Invoke-Step 'registration 1-4 (remote)' { python -m coverage run --branch --source=src --append test/live/registration/registration_http_six_step_tb.py --work-dir test/artifacts/env/reg-six-remote-14 --user vbsixremote --daemon-port 65133 --root /home/Gent/.virtuoso-bridge/vbsixremote --stop-after-deploy --out test/artifacts/env/reg-six-remote-14/evidence.json | Out-Null }

# ---- HTTP mixed workload (Windows client) ---------------------------------------
Invoke-Step 'http mixed stress (windows)' { python -m coverage run --branch --source=src --append test/live/stress/http_mixed_stress_tb.py --work-dir test/artifacts/env/http-stress2 --remote-token vb-vblog --remote-daemon-port 65121 --remote-root /home/Gent/.virtuoso-bridge/vblog --workers 6 --rounds 6 --out test/artifacts/env/http-stress2/evidence.json | Out-Null }

# ---- real machine TBs -------------------------------------------------------------
# Live daemon used here is the standing ``vb-vblog`` instance (65121).  The
# historical vb-vb11 token/daemon no longer exists, and a gate that can never
# pass is worse than useless: point it at an instance that is part of the
# documented environment (test/docs/推荐测试环境.md §3).
Invoke-Step 'real five interfaces' { python -m coverage run --branch --source=src --append test/live/transport/cov_remote_real.py --work-dir test/artifacts/env/log-vblog --token vb-vblog | Out-Null }
Invoke-Step 'real registration 1-4' { python -m coverage run --branch --source=src --append test/semi/registration/cov_registration_real.py --work-dir test/artifacts/env/cov-registration --user covreg --token cov-token --port 65112 | Out-Null }
Invoke-Step 'real CDS.log matrix' { python -m coverage run --branch --source=src --append test/semi/transport/log_matrix_real_tb.py --work-dir test/artifacts/env/log-vblog --token vb-vblog --out test/artifacts/evidence/log-matrix-real-green.json | Out-Null }
Invoke-Step 'one-shot channel burst' { python -m coverage run --branch --source=src --append test/semi/transport/one_shot_burst_tb.py --work-dir test/artifacts/env/one-shot-burst --token vb-vblog --out test/artifacts/evidence/one-shot-burst-green.json | Out-Null }
# Transport primitives for *both* SSH backends against a real sshd (no
# Virtuoso): run_command/upload/download/persistent shell/concurrency.  This is
# the only step that measures the Paramiko connect/forward paths, which the
# offline fakes cannot reach.
Invoke-Step 'ssh backends semi-real' { python -m coverage run --branch --source=src --append test/semi/transport/ssh_backend_semi_tb.py --host $WslHost --out test/artifacts/evidence/ssh-backend-semi.json | Out-Null }
Invoke-Step 'role credential isolation semi-real' { python -m coverage run --branch --source=src --append test/semi/transport/role_credential_isolation_tb.py --host $WslHost --out test/artifacts/evidence/role-credential-isolation.json | Out-Null }

# ---- upper-layer package TBs -------------------------------------------------------
# Run through the *direct* transport on purpose: the package code then executes
# inside this process, so its coverage is really measured.  With --transport http
# only the urllib client would be counted - which is exactly why these modules sat
# near 16% while their TBs were green (measured 2026-09-22: layout.py 16.5% -> 79%
# purely by switching the measurement on).
if (-not $SkipPackages) {
    foreach ($tb in @('schematic', 'symbol', 'layout', 'cellview', 'verilog',
                      'veriloga', 'skillref', 'infra', 'maestro', 'spectre')) {
        Invoke-Step "package TB: $tb (direct)" {
            python -m coverage run --branch --source=src --append "test/live/packages/${tb}_e2e_tests.py" --transport direct
        }
    }
}

# ---- extended: WSL client equivalence + saturation -------------------------------
if ($IncludeExtended) {
    Invoke-Step 'sync tree to WSL' {
        tar -czf test/artifacts/tmp/wsl_sync.tgz `
            --exclude=test/artifacts --exclude='*/__pycache__' `
            src test/offline test/semi test/live test/shared/fixtures test/shared/runners
        ssh $WslHost "mkdir -p $WslSandbox/repo"
        scp -q test/artifacts/tmp/wsl_sync.tgz "${WslHost}:$WslSandbox/wsl_sync.tgz"
        ssh $WslHost "tar -xzf $WslSandbox/wsl_sync.tgz -C $WslSandbox/repo"
        Remove-Item test/artifacts/tmp/wsl_sync.tgz -Force
    }
    Invoke-Step 'http mixed stress (wsl client)' {
        $wslRun = "$WslSandbox/runs/http-$(Get-Date -Format yyyyMMddHHmmss)"
        ssh $WslHost "mkdir -p $wslRun"
        ssh $WslHost "cd $WslSandbox/repo && PYTHONPATH=src $WslPython test/live/stress/http_mixed_stress_tb.py --work-dir $wslRun --remote-host localhost --remote-token vb-vblog --remote-daemon-port 65121 --remote-root /home/Gent/.virtuoso-bridge/vblog --workers 6 --rounds 6 --out $wslRun/evidence.json"
        scp -q "${WslHost}:$wslRun/evidence.json" test/artifacts/evidence/http-stress-wsl-client.json
        ssh $WslHost "rm -rf $wslRun"
    }
    Invoke-Step 'saturation profile' { python -m coverage run --branch --source=src --append test/live/stress/http_mixed_stress_tb.py --work-dir test/artifacts/env/http-stress-sat --remote-token vb-vblog --remote-daemon-port 65121 --remote-root /home/Gent/.virtuoso-bridge/vblog --workers 24 --rounds 3 --local-pool 4 --max-attempts 60 --out test/artifacts/env/http-stress-sat/evidence.json | Out-Null }
}

# ---- coverage report --------------------------------------------------------------
# Record what this run did NOT include, next to the numbers it produced.
$script:skippedSteps | ConvertTo-Json -Depth 3 |
    Out-File -Encoding utf8 "$evidenceDir/coverage-run-skipped.json"

# ``coverage report`` shows branch columns automatically when the data file was
# produced with ``--branch``; it has no --branch flag of its own.
Invoke-Step 'coverage text report' { python -m coverage report -m --skip-covered | Out-File -Encoding utf8 test/artifacts/evidence/coverage-combined.txt }
Invoke-Step 'coverage json report' { python -m coverage json -o test/artifacts/evidence/coverage-combined.json }
# ``percent_covered`` mixes statements and branches, so the gate is explicit:
# statements are gated by -FailUnder, branches only when -BranchFailUnder > 0.
Invoke-Step 'coverage threshold' {
    python -c "import json,sys; t=json.load(open('test/artifacts/evidence/coverage-combined.json',encoding='utf-8'))['totals']; s=t['percent_statements_covered']; b=t.get('percent_branches_covered'); print(f'statements={s:.2f}% branches={b if b is None else round(b,2)}%'); sys.exit(0 if s >= $FailUnder and (b is None or b >= $BranchFailUnder) else 1)"
}
