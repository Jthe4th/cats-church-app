param(
  [int]$Port = 8000,
  [string]$BindAddress = "0.0.0.0",
  [switch]$SkipAdminUser,
  [switch]$NoStart,
  [switch]$WaitAtEnd
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$LogDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $LogDir)) {
  New-Item -ItemType Directory -Path $LogDir | Out-Null
}
$LogPath = Join-Path $LogDir "deploy-windows.log"
Start-Transcript -Path $LogPath -Append | Out-Null

function Complete($Code) {
  Stop-Transcript | Out-Null
  if ($WaitAtEnd) {
    Write-Host ""
    Read-Host "Press Enter to close this window"
  }
  exit $Code
}

function Invoke-Step {
  param(
    [string]$Message,
    [scriptblock]$Command
  )

  Write-Host ""
  Write-Host "==> $Message" -ForegroundColor Cyan
  & $Command
}

try {
  if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found. Install Python 3.12+ from python.org, then reopen PowerShell."
  }

  Invoke-Step "Creating virtual environment if needed" {
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
      python -m venv .venv
    }
  }

  $Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

  Invoke-Step "Installing Python packages" {
    & $Python -m pip install --upgrade pip
    & $Python -m pip install -r requirements.txt
  }

  Invoke-Step "Applying database migrations" {
    & $Python manage.py migrate
  }

  if (-not $SkipAdminUser) {
    Write-Host ""
    $createAdmin = Read-Host "Create or update an admin login now? Type Y to run createsuperuser"
    if ($createAdmin -eq "Y" -or $createAdmin -eq "y") {
      Invoke-Step "Creating admin user" {
        & $Python manage.py createsuperuser
      }
    }
  }

  Invoke-Step "Collecting static files" {
    & $Python manage.py collectstatic --noinput
  }

  Invoke-Step "Checking app configuration" {
    & $Python manage.py check
  }

  Write-Host ""
  Write-Host "Deployment setup complete." -ForegroundColor Green
  Write-Host "Log file:   $LogPath"
  Write-Host "Host URL:   http://127.0.0.1:$Port/admin/"
  Write-Host "LAN URL:    http://<this-pc-name-or-ip>:$Port/kiosk/?kiosk=kiosk1"
  Write-Host ""
  Write-Host "If Windows Firewall prompts, allow private-network access for Python."

  if (-not $NoStart) {
    Invoke-Step "Starting Waitress on $BindAddress`:$Port" {
      & $Python -m waitress --listen="$BindAddress`:$Port" cats.wsgi:application
    }
  }
} catch {
  Write-Host ""
  Write-Host "Deployment failed:" -ForegroundColor Red
  Write-Host $_.Exception.Message -ForegroundColor Red
  Write-Host ""
  Write-Host "Log file: $LogPath"
  Complete 1
}

Complete 0
