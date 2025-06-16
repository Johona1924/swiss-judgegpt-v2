# Prefer python3.11, then fall back to python, then python3
$pythonCmd = Get-Command python3.11 -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
}
if (-not $pythonCmd) {
    $pythonCmd = Get-Command python3 -ErrorAction SilentlyContinue
}

if (-not $pythonCmd) {
    Write-Host "No suitable Python installation found (expected python3.11, python, or python3)"
    exit 1
}

# Show the Python interpreter and version selected
Write-Host "Using Python interpreter: $(($pythonCmd).Source)"
& ($pythonCmd).Source -c "import sys; print('Python version:', sys.version)"

Write-Host 'Creating python virtual environment ".venv"'
Start-Process -FilePath ($pythonCmd).Source -ArgumentList "-m venv ./.venv" -Wait -NoNewWindow

$venvPythonPath = "./.venv/scripts/python.exe"
if (Test-Path -Path "/usr") {
  # fallback to Linux venv path
  $venvPythonPath = "./.venv/bin/python"
}

Write-Host 'Installing dependencies from "requirements.txt" into virtual environment'
Start-Process -FilePath $venvPythonPath -ArgumentList "-m pip install -r app/backend/requirements.txt" -Wait -NoNewWindow