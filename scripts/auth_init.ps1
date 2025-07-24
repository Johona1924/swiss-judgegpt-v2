Write-Host "Checking if authentication should be setup..."

$AZURE_USE_AUTHENTICATION = (azd env get-value AZURE_USE_AUTHENTICATION)
$USE_AUTH0_AUTHENTICATION = (azd env get-value USE_AUTH0_AUTHENTICATION)
$AZURE_ENABLE_GLOBAL_DOCUMENT_ACCESS = (azd env get-value AZURE_ENABLE_GLOBAL_DOCUMENT_ACCESS)
$AZURE_ENFORCE_ACCESS_CONTROL = (azd env get-value AZURE_ENFORCE_ACCESS_CONTROL)
$USE_CHAT_HISTORY_COSMOS = (azd env get-value USE_CHAT_HISTORY_COSMOS)

if ($AZURE_USE_AUTHENTICATION -eq "true" -and $USE_AUTH0_AUTHENTICATION -eq "true") {
  Write-Host "Both AZURE_USE_AUTHENTICATION and USE_AUTH0_AUTHENTICATION are set to true. Please choose only one authentication method."
  Exit 1
}

if ($AZURE_ENABLE_GLOBAL_DOCUMENT_ACCESS -eq "true") {
  if ($AZURE_ENFORCE_ACCESS_CONTROL -ne "true") {
    Write-Host "AZURE_ENABLE_GLOBAL_DOCUMENT_ACCESS is set to true, but AZURE_ENFORCE_ACCESS_CONTROL is not set to true. Please set it and retry."
    Exit 1
  }
}

if ($USE_CHAT_HISTORY_COSMOS -eq "true") {
  if ($AZURE_USE_AUTHENTICATION -ne "true" -and $USE_AUTH0_AUTHENTICATION -ne "true") {
    Write-Host "USE_CHAT_HISTORY_COSMOS is set to true, but neither AZURE_USE_AUTHENTICATION nor USE_AUTH0_AUTHENTICATION is set to true. Please set one and retry."
    Exit 1
  }
}

if ($USE_AUTH0_AUTHENTICATION -eq "true") {
  Write-Host "USE_AUTH0_AUTHENTICATION is set to true. Skipping Microsoft Entra application setup."
  Exit 0
}

if ($AZURE_USE_AUTHENTICATION -ne "true") {
  Write-Host "AZURE_USE_AUTHENTICATION is not set, skipping authentication setup."
  Exit 0
}

. ./scripts/load_python_env.ps1

$venvPythonPath = "./.venv/scripts/python.exe"
if (Test-Path -Path "/usr") {
  # fallback to Linux venv path
  $venvPythonPath = "./.venv/bin/python"
}

Start-Process -FilePath $venvPythonPath -ArgumentList "./scripts/auth_init.py" -Wait -NoNewWindow
