$AZURE_USE_AUTHENTICATION = (azd env get-value AZURE_USE_AUTHENTICATION)
$USE_APPSERVICE_AUTHENTICATION = (azd env get-value USE_APPSERVICE_AUTHENTICATION)

if ($USE_APPSERVICE_AUTHENTICATION -eq "true") {
  Write-Host "USE_APPSERVICE_AUTHENTICATION is set to true. Skipping Microsoft Entra application updates."
  Exit 0
}

if ($AZURE_USE_AUTHENTICATION -ne "true") {
  Exit 0
}

. ./scripts/load_python_env.ps1

$venvPythonPath = "./.venv/scripts/python.exe"
if (Test-Path -Path "/usr") {
  # fallback to Linux venv path
  $venvPythonPath = "./.venv/bin/python"
}

Start-Process -FilePath $venvPythonPath -ArgumentList "./scripts/auth_update.py" -Wait -NoNewWindow
