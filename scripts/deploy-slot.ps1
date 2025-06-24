param (
    [string]$SlotName
)

if ([string]::IsNullOrEmpty($SlotName)) {
    Write-Error "Usage: .\deploy-slot.ps1 -SlotName <slot-name>"
    exit 1
}

# Set parent of script as current location
Set-Location $PSScriptRoot\..

Write-Host "Loading azd .env file from current environment"
foreach ($line in (& azd env get-values)) {
    if ($line -match "([^=]+)=(.*)") {
        $key = $matches[1]
        $value = $matches[2] -replace '^"|"$'
        Set-Item -Path "env:\$key" -Value $value
    }
}

if (-not $env:AZURE_APP_SERVICE -or -not $env:AZURE_RESOURCE_GROUP) {
    Write-Error "AZURE_APP_SERVICE or AZURE_RESOURCE_GROUP environment variables not set. Make sure you have run 'azd provision'."
    exit 1
}

Write-Host "Checking if slot '$SlotName' exists..."
$slotExists = az webapp deployment slot list --resource-group "$env:AZURE_RESOURCE_GROUP" --name "$env:AZURE_APP_SERVICE" --query "[?name=='$SlotName']" -o tsv
if ([string]::IsNullOrEmpty($slotExists)) {
    Write-Host "Slot '$SlotName' does not exist. Creating it..."
    az webapp deployment slot create --name "$env:AZURE_APP_SERVICE" --resource-group "$env:AZURE_RESOURCE_GROUP" --slot "$SlotName" --configuration-source "$env:AZURE_APP_SERVICE"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create deployment slot."
        exit 1
    }
    Write-Host "Slot '$SlotName' created successfully."
} else {
    Write-Host "Slot '$SlotName' already exists."
}

Write-Host "Building frontend..."
Push-Location app\frontend
npm install
npm run build
Pop-Location

Write-Host "Creating deployment package..."
Compress-Archive -Path app\* -DestinationPath deployment.zip -Force

Write-Host "Deploying to slot '$SlotName' of app '$env:AZURE_APP_SERVICE' in resource group '$env:AZURE_RESOURCE_GROUP'..."
az webapp deployment source config-zip --resource-group "$env:AZURE_RESOURCE_GROUP" --name "$env:AZURE_APP_SERVICE" --slot "$SlotName" --src "deployment.zip" --timeout 900

Write-Host "Cleaning up..."
Remove-Item deployment.zip

Write-Host "Deployment to slot '$SlotName' completed."