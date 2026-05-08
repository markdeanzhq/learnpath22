param(
    [string]$Mode = "all"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch {
}

$ScriptDir = Split-Path -Parent $PSCommandPath
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$Backend = Join-Path $RepoRoot "backend"
$Frontend = Join-Path $RepoRoot "frontend"
$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { Join-Path $Backend ".venv\Scripts\python.exe" }
$NpmBin = if ($env:NPM_BIN) { $env:NPM_BIN } else { "npm.cmd" }
$EvidenceScript = Join-Path $ScriptDir "final_check_evidence.py"
$env:PYTHONIOENCODING = "utf-8"

function Show-Usage {
    Write-Host "Usage: powershell -ExecutionPolicy Bypass -File scripts\final_check.ps1 [all|evidence-only|skip-frontend|audit-log]"
    Write-Host ""
    Write-Host "all            Run backend tests, frontend tests, frontend build, then print formal experiment validation report."
    Write-Host "evidence-only  Print formal experiment validation report only."
    Write-Host "skip-frontend  Run backend tests and print formal experiment validation report."
    Write-Host "audit-log      Print screenshot-friendly experiment process log only."
}

function Invoke-Step {
    param(
        [string]$Title,
        [scriptblock]$Action
    )
    Write-Host ""
    Write-Host "========== $Title =========="
    & $Action
}

function Require-File {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing required file: $Path"
    }
}

function Invoke-CheckedCommand {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Invoke-BackendTests {
    Require-File $PythonBin
    $oldPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = $Backend
    try {
        Invoke-CheckedCommand $PythonBin @("-m", "pytest", (Join-Path $Backend "tests"), "-q")
    } finally {
        $env:PYTHONPATH = $oldPythonPath
    }
}

function Invoke-FrontendTests {
    Invoke-CheckedCommand $NpmBin @("--prefix", $Frontend, "run", "test:run")
}

function Invoke-FrontendBuild {
    Invoke-CheckedCommand $NpmBin @("--prefix", $Frontend, "run", "build")
}

function Show-EvidenceSummary {
    Require-File $PythonBin
    Require-File $EvidenceScript
    $env:REPO_ROOT = $RepoRoot
    Invoke-CheckedCommand $PythonBin @($EvidenceScript)
}

function Show-AuditLog {
    Require-File $PythonBin
    Require-File $EvidenceScript
    $env:REPO_ROOT = $RepoRoot
    Invoke-CheckedCommand $PythonBin @($EvidenceScript, "--audit-log")
}

switch ($Mode) {
    "all" {
        Invoke-Step "Backend pytest" { Invoke-BackendTests }
        Invoke-Step "Frontend Vitest" { Invoke-FrontendTests }
        Invoke-Step "Frontend build" { Invoke-FrontendBuild }
        Invoke-Step "Paper experiment validation report" { Show-EvidenceSummary }
    }
    "evidence-only" {
        Invoke-Step "Paper experiment validation report" { Show-EvidenceSummary }
    }
    "--evidence-only" {
        Invoke-Step "Paper experiment validation report" { Show-EvidenceSummary }
    }
    "skip-frontend" {
        Invoke-Step "Backend pytest" { Invoke-BackendTests }
        Invoke-Step "Paper experiment validation report" { Show-EvidenceSummary }
    }
    "--skip-frontend" {
        Invoke-Step "Backend pytest" { Invoke-BackendTests }
        Invoke-Step "Paper experiment validation report" { Show-EvidenceSummary }
    }
    "audit-log" {
        Invoke-Step "Paper experiment audit log" { Show-AuditLog }
    }
    "--audit-log" {
        Invoke-Step "Paper experiment audit log" { Show-AuditLog }
    }
    "help" { Show-Usage }
    "-h" { Show-Usage }
    "--help" { Show-Usage }
    default {
        Show-Usage
        exit 1
    }
}
