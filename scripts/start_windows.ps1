param(
  [int]$Port = 8000,
  [string]$BindAddress = "0.0.0.0",
  [switch]$WaitAtEnd
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$LogDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $LogDir)) {
  New-Item -ItemType Directory -Path $LogDir | Out-Null
}

$OutLog = Join-Path $LogDir "waitress-out.log"
$ErrLog = Join-Path $LogDir "waitress-error.log"
$LocalUrl = "http://127.0.0.1:$Port/admin/"
$KioskUrl = "http://<this-pc-name-or-ip>:$Port/kiosk/?kiosk=kiosk1"

function Complete($Code) {
  if ($WaitAtEnd) {
    Write-Host ""
    Read-Host "Press Enter to close this window"
  }
  exit $Code
}

function Fail($Message) {
  Write-Host ""
  Write-Host "FAILED: $Message" -ForegroundColor Red
  Write-Host "Run first-time setup with: .\scripts\deploy_windows.cmd"
  Write-Host "Error log: $ErrLog"
  Complete 1
}

function Test-AppReady {
  try {
    $response = Invoke-WebRequest -Uri $LocalUrl -UseBasicParsing -TimeoutSec 3
    return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
  } catch {
    return $false
  }
}

Write-Host "Starting Welcome System..." -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  Fail "Virtual environment Python was not found at .venv\Scripts\python.exe."
}

try {
  & $Python -c "import waitress" 2>$null
  if ($LASTEXITCODE -ne 0) {
    Fail "Waitress is not installed in the virtual environment."
  }
} catch {
  Fail "Could not check whether Waitress is installed."
}

if (Test-AppReady) {
  Write-Host ""
  Write-Host "SUCCESS: Welcome System is already running." -ForegroundColor Green
  Write-Host "Admin URL:  $LocalUrl"
  Write-Host "Kiosk URL:  $KioskUrl"
  Complete 0
}

$portInUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($portInUse) {
  $owners = ($portInUse | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
  Fail "Port $Port is already in use by process id(s): $owners, but the app did not respond at $LocalUrl."
}

$arguments = @(
  "-m",
  "waitress",
  "--listen=$BindAddress`:$Port",
  "cats.wsgi:application"
)

try {
  $process = Start-Process `
    -FilePath $Python `
    -ArgumentList $arguments `
    -WorkingDirectory $ProjectRoot `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -PassThru
} catch {
  Fail "Could not start Waitress. $($_.Exception.Message)"
}

Write-Host "Waitress process id: $($process.Id)"
Write-Host "Waiting for app to respond..."

for ($attempt = 1; $attempt -le 20; $attempt++) {
  Start-Sleep -Seconds 1
  if ($process.HasExited) {
    Fail "Waitress exited immediately. Check the error log."
  }
  if (Test-AppReady) {
    Write-Host ""
    Write-Host "SUCCESS: Welcome System is running." -ForegroundColor Green
    Write-Host "Admin URL:  $LocalUrl"
    Write-Host "Kiosk URL:  $KioskUrl"
    Write-Host "Output log: $OutLog"
    Write-Host "Error log:  $ErrLog"
    Write-Host ""
    Write-Host "To stop it later, run:"
    Write-Host "Stop-Process -Id $($process.Id)"
    Complete 0
  }
}

Fail "Waitress started but did not respond at $LocalUrl within 20 seconds."
