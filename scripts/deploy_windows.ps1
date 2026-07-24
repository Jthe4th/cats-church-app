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

function Ensure-Git {
  if (Get-Command git -ErrorAction SilentlyContinue) {
    Write-Host "Git is ready."
    return
  }

  $Winget = Get-Command winget -ErrorAction SilentlyContinue
  if (-not $Winget) {
    throw "Git is required for Welcome System updates. Windows could not find winget to install it automatically. Install Git for Windows from https://git-scm.com/download/win, then run this setup again."
  }

  Write-Host "Git for Windows is not installed. Installing it now..." -ForegroundColor Yellow
  & winget install --id Git.Git --exact --source winget --silent --accept-source-agreements --accept-package-agreements
  if ($LASTEXITCODE -ne 0) {
    throw "Git for Windows could not be installed automatically. Install it from https://git-scm.com/download/win, then run this setup again."
  }

  $GitCommandDirectories = @(
    (Join-Path $env:ProgramFiles "Git\cmd"),
    (Join-Path ${env:ProgramFiles(x86)} "Git\cmd"),
    (Join-Path $env:LOCALAPPDATA "Programs\Git\cmd")
  )
  foreach ($Directory in $GitCommandDirectories) {
    if ((Test-Path $Directory) -and ($env:Path -notlike "*$Directory*")) {
      $env:Path = "$Directory;$env:Path"
    }
  }

  if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git was installed but is not yet available to this setup window. Close this window, open it again, and rerun setup."
  }
  Write-Host "Git for Windows is ready."
}

function Ensure-GitRepository {
  & git rev-parse --is-inside-work-tree 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) {
    Write-Host "This folder is connected to GitHub."
    return
  }

  Write-Host "Connecting this Welcome System folder to GitHub..." -ForegroundColor Yellow
  & git init
  if ($LASTEXITCODE -ne 0) { throw "Could not initialize this folder for GitHub updates." }
  & git remote remove origin 2>$null
  & git remote add origin "https://github.com/Jthe4th/cats-church-app.git"
  if ($LASTEXITCODE -ne 0) { throw "Could not connect this folder to the Welcome System GitHub repository." }
  & git fetch --quiet origin main
  if ($LASTEXITCODE -ne 0) { throw "Could not download Welcome System from GitHub." }
  & git reset --hard FETCH_HEAD
  if ($LASTEXITCODE -ne 0) { throw "Could not restore the Welcome System application files from GitHub." }
  Write-Host "This folder is now connected to GitHub."
}

try {
  Invoke-Step "Checking for Git updates support" {
    Ensure-Git
  }

  Invoke-Step "Connecting Welcome System to GitHub" {
    Ensure-GitRepository
  }

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
