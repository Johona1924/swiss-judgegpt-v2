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
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to create deployment slot."
            exit 1
        }
        Write-Host "Slot '$SlotName' created successfully."

        # Assign system managed identity to the newly created slot
        Write-Host "Enabling system managed identity for slot '$SlotName'..."
        az webapp identity assign --name "$AppServiceName" --resource-group "$ResourceGroup" --slot "$SlotName"
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to assign system managed identity to slot."
            exit 1
        }

        # Get the principal ID of the slot's managed identity
        Write-Host "Getting principal ID for slot managed identity..."
        $slotPrincipalId = az webapp identity show --name "$AppServiceName" --resource-group "$ResourceGroup" --slot "$SlotName" --query "principalId" -o tsv
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrEmpty($slotPrincipalId)) {
            Write-Error "Failed to get principal ID for slot managed identity."
            exit 1
        }
        Write-Host "Slot principal ID: $slotPrincipalId"

        # Assign RBAC roles at resource group level
        Write-Host "Assigning RBAC roles to slot managed identity..."
        $roles = @(
            "1407120a-92aa-4202-b7e9-c0e197c71c8f",  # Search Index Data Reader
            "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd",  # Cognitive Services OpenAI User
            "f2dc8367-1007-4938-bd23-fe263f013447",  # Cognitive Services Speech User
            "2a2b9908-6ea1-4ae2-8e65-a410df84e7d1",  # Storage Blob Data Reader
            "acdd72a7-3385-48ef-bd42-f606fba81ae7"   # Reader
        )

        foreach ($roleId in $roles) {
            Write-Host "Assigning role $roleId..."
            az role assignment create --assignee "$slotPrincipalId" --role "$roleId" --scope "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup"
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Failed to assign role $roleId to slot managed identity. Continuing..."
            }
        }

        # Assign Cosmos DB Built-in Data Contributor role if Cosmos DB is configured
        if ($env:AZURE_COSMOSDB_ACCOUNT -and $env:USE_CHAT_HISTORY_COSMOS -eq "true") {
            Write-Host "Assigning Cosmos DB Built-in Data Contributor role..."
            $cosmosDbAccount = $env:AZURE_COSMOSDB_ACCOUNT
            $cosmosDbResourceGroup = if ($env:AZURE_COSMOSDB_RESOURCE_GROUP) { $env:AZURE_COSMOSDB_RESOURCE_GROUP } else { $ResourceGroup }
            
            # Get Cosmos DB account scope
            $cosmosDbScope = az cosmosdb show --resource-group "$cosmosDbResourceGroup" --name "$cosmosDbAccount" --query "id" -o tsv
            if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrEmpty($cosmosDbScope)) {
                # Assign Cosmos DB Built-in Data Contributor role (role definition ID: 00000000-0000-0000-0000-000000000002)
                $cosmosDbRoleDefinitionId = "$cosmosDbScope/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
                az cosmosdb sql role assignment create --resource-group "$cosmosDbResourceGroup" --account-name "$cosmosDbAccount" --role-definition-id "$cosmosDbRoleDefinitionId" --principal-id "$slotPrincipalId" --scope "$cosmosDbScope"
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "Successfully assigned Cosmos DB Built-in Data Contributor role."
                } else {
                    Write-Warning "Failed to assign Cosmos DB Built-in Data Contributor role. Continuing..."
                }
            } else {
                Write-Warning "Could not find Cosmos DB account '$cosmosDbAccount'. Skipping Cosmos DB role assignment."
            }
        } else {
            Write-Host "Cosmos DB not configured or chat history not enabled. Skipping Cosmos DB role assignment."
        }
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




