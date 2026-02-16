$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
  python -m venv .venv
}

. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python -m waitress --listen=0.0.0.0:8000 cats.wsgi:application
