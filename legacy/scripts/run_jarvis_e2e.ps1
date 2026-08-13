param(
  [string]$Song = "Ultralight Beam",
  [string]$Artist = "Kanye West",
  [string]$Section = "chorus",
  [int]$Track = 0,
  [ValidateSet("full","verify-only","resume")]
  [string]$Mode = "full",
  [string]$AbletonExe = ""
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"
if (!(Test-Path $VenvPython)) {
  throw "Python venv not found: $VenvPython"
}

$EnvPath = Join-Path $ProjectRoot ".env"
if (Test-Path $EnvPath) {
  Get-Content $EnvPath | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
    $parts = $_ -split '=', 2
    if ($parts.Count -eq 2) {
      [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim())
    }
  }
}

$Args = @(
  "scripts/e2e_orchestrator.py",
  "--mode", $Mode,
  "--song", $Song,
  "--artist", $Artist,
  "--section", $Section,
  "--track", $Track
)

if ($AbletonExe -and $AbletonExe.Trim().Length -gt 0) {
  $Args += @("--ableton-exe", $AbletonExe)
}

Write-Host "[E2E] Starting Jarvis E2E run..." -ForegroundColor Cyan
& $VenvPython @Args
$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
  Write-Host "[E2E] Success." -ForegroundColor Green
} else {
  Write-Host "[E2E] Failed with exit code $exitCode" -ForegroundColor Red
}

exit $exitCode
