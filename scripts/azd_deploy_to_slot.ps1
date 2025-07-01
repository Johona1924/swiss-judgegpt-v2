[CmdletBinding()]
param (
    [Parameter(Mandatory = $true, HelpMessage = "The name of the deployment slot.")]
    [string]$SlotName
)

# Use a try/finally block to ensure cleanup of the temporary JSON file
$tempJsonFile = Join-Path ([System.IO.Path]::GetTempPath()) ([System.IO.Path]::GetRandomFileName() + ".json")
$tempPackageFile = Join-Path ([System.IO.Path]::GetTempPath()) ([System.IO.Path]::GetRandomFileName() + ".zip")
try {
    # Set working directory to project root to ensure azd and git commands work correctly
    Set-Location $PSScriptRoot\..

    # --- Load Environment and Gather Information ---
    Write-Host "Loading azd environment variables..."
    $azdEnv = azd env get-values
    foreach ($line in ($azdEnv)) {
        if ($line -match "([^=]+)=(.*)") {
            $key = $matches[1]
            $value = $matches[2] -replace '^"|"$'
            Set-Item -Path "env:\$key" -Value $value
        }
    }

    $azdEnvName = $env:AZURE_ENV_NAME
    $gitBranchName = (git rev-parse --abbrev-ref HEAD).Trim()
    $ResourceGroup = $env:AZURE_RESOURCE_GROUP
    $AppServiceName = $env:AZURE_APP_SERVICE
    $SubscriptionId = $env:AZURE_SUBSCRIPTION_ID
    $SubscriptionName = (az account show --subscription $SubscriptionId --query "name" -o tsv)

    # --- User Confirmation ---
    $confirmationMessage = @"
Please confirm the following deployment details:
- Azd Environment:  $azdEnvName
- Git Branch:       $gitBranchName
- Subscription:     $SubscriptionName ($SubscriptionId)
- Resource Group:   $ResourceGroup
- App Service:      $AppServiceName
- Target Slot:      $SlotName

Are you sure you want to proceed with the deployment? (y/n)
"@
    $response = Read-Host -Prompt $confirmationMessage
    if ($response -ne 'y') {
        Write-Host "Deployment cancelled by user."
        exit 0
    }

    # --- Validate Environment ---
    Write-Host "Checking Azure login and subscription..."
    $currentSubscription = az account show --query "id" -o tsv
    if ($LASTEXITCODE -ne 0) {
        Write-Error "You are not logged into Azure. Please run 'az login' and try again."
        exit 1
    }
    if ($currentSubscription -ne $SubscriptionId) {
        Write-Error "Logged in to wrong Azure subscription. Please run 'az account set --subscription $SubscriptionId'."
        exit 1
    }
    Write-Host "Azure login and subscription are valid."

    if (-not $AppServiceName -or -not $ResourceGroup) {
        Write-Error "AZURE_APP_SERVICE or AZURE_RESOURCE_GROUP environment variables not set. Make sure you have run 'azd provision'."
        exit 1
    }

    # --- Package Application ---
    Write-Host "Packaging service backend..."
    azd package backend --output-path $tempPackageFile
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to package the application. Aborting."
        exit 1
    }
    $PackagePath = $tempPackageFile
    Write-Host "Application packaged successfully to '$PackagePath'."

    # --- Check/Create Deployment Slot ---
    Write-Host "Checking if slot '$SlotName' exists..."
    $slotExists = az webapp deployment slot list --resource-group "$ResourceGroup" --name "$AppServiceName" --query "[?name=='$SlotName']" -o tsv
    if ([string]::IsNullOrEmpty($slotExists)) {
        Write-Host "Slot '$SlotName' does not exist. Creating it..."
        az webapp deployment slot create --name "$AppServiceName" --resource-group "$ResourceGroup" --slot "$SlotName" --configuration-source "$AppServiceName"
        # TODO : assign system managed identity, give the following resource-group wide RBAC: Search Index Data Reader, Cognitive Services OpenAI User, Cognitive Services Speech User, Storage Blob Data Reader, Reader
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to create deployment slot."
            exit 1
        }
        Write-Host "Slot '$SlotName' created successfully."
    } else {
        Write-Host "Slot '$SlotName' already exists."
    }

    # --- Deploy to Slot ---
    Write-Host "Deploying to slot '$SlotName' in AppService '$AppServiceName'..."
    az webapp deploy --resource-group $ResourceGroup --name $AppServiceName --src-path $PackagePath --slot $SlotName --type zip --track-status false
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to deploy webapp to slot."
        exit 1
    }
    Write-Host "Deployment to slot initiated. App service will build the package in the background."

    # --- Configure Slot Settings ---
    Write-Host "Updating app configuration and app settings for slot '$SlotName'..."
    az webapp config set --startup-file "python3 -m gunicorn main:app" --name $AppServiceName --resource-group $ResourceGroup --slot $SlotName
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to set startup file."
        exit 1
    }

    # Create a JSON file with all environment variables plus the SCM setting
    $settings = @()
    foreach ($line in ($azdEnv)) {
        if ($line -match "([^=]+)=(.*)") {
            $settings += @{
                name        = $matches[1]
                value       = $matches[2] -replace '^"|"$'
                slotSetting = $false
            }
        }
    }
    $settings += @{
        name        = "WEBSITE_WEBDEPLOY_USE_SCM"
        value       = "false"
        slotSetting = $false
    }

    $settings | ConvertTo-Json | Out-File -FilePath $tempJsonFile -Encoding utf8

    az webapp config appsettings set --resource-group $ResourceGroup --name $AppServiceName --slot $SlotName --settings "@$tempJsonFile"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to set app settings from JSON file."
        exit 1
    }
    Write-Host "Successfully updated app configuration and settings."

    # --- Final Success Message ---
    Write-Host "------------------------------------------------------------------"
    Write-Host "✅ Successfully deployed to slot '$SlotName'."
    Write-Host "------------------------------------------------------------------"

}
catch {
    Write-Error "An unexpected error occurred: $($_.Exception.Message)"
    exit 1
}
finally {
    # --- Cleanup ---
    if (Test-Path $tempJsonFile) {
        Remove-Item $tempJsonFile -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path $tempPackageFile) {
        Remove-Item $tempPackageFile -Force -ErrorAction SilentlyContinue
    }
}




