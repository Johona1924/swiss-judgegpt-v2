[CmdletBinding()]
param (
    [Parameter(Mandatory = $true, HelpMessage = "The name of the deployment slot.")]
    [string]$SlotName
)

# Helper: run a CLI command given as a string-array, suppress JSON, print success or exit on error
function Run-Command {
    param(
        [Parameter(Mandatory=$true)][string[]]$Command,
        [Parameter(Mandatory=$true)][string]$SuccessMessage
    )
    # split out executable + args
    $exe  = $Command[0]
    $args = if ($Command.Count -gt 1) { $Command[1..($Command.Count-1)] } else { @() }

    # invoke, capturing all output
    $output = & $exe @args 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error $output
        exit 1
    }
    Write-Host $SuccessMessage
    return $output
}

# Temp files
$tempJsonFile    = Join-Path ([IO.Path]::GetTempPath()) ([IO.Path]::GetRandomFileName() + ".json")
$tempPackageFile = Join-Path ([IO.Path]::GetTempPath()) ([IO.Path]::GetRandomFileName() + ".zip")

try {
    # — Set working directory —
    Set-Location $PSScriptRoot\..
    Write-Host "Working directory set to project root."

    # — Load azd environment —
    $azdEnv = Run-Command `
      -Command @("azd", "env", "get-values") `
      -SuccessMessage "Loaded azd environment variables."
    foreach ($line in $azdEnv) {
        if ($line -match "([^=]+)=(.*)") {
            $key   = $matches[1]
            $value = $matches[2] -replace '^"|"$'
            Set-Item -Path "env:\$key" -Value $value
        }
    }

    # — Gather basic info —
    $azdEnvName       = $env:AZURE_ENV_NAME
    $gitBranchName    = (git rev-parse --abbrev-ref HEAD).Trim()
    $ResourceGroup    = $env:AZURE_RESOURCE_GROUP
    $AppServiceName   = $env:AZURE_APP_SERVICE
    $SubscriptionId   = $env:AZURE_SUBSCRIPTION_ID
    $SubscriptionName = Run-Command `
      -Command @("az", "account", "show", "--subscription", $SubscriptionId, "--query", "name", "-o", "tsv") `
      -SuccessMessage "Retrieved Azure subscription name."

    # — Confirm with user —
    $confirm = @"
Please confirm the following deployment details:
- Azd Environment:  $azdEnvName
- Git Branch:       $gitBranchName
- Subscription:     $SubscriptionName ($SubscriptionId)
- Resource Group:   $ResourceGroup
- App Service:      $AppServiceName
- Target Slot:      $SlotName

Proceed? (y/n)
"@
    if ((Read-Host -Prompt $confirm) -ne 'y') {
        Write-Host "Deployment cancelled by user."
        exit 0
    }

    # — Validate login & subscription —
    $currentSubscription = Run-Command `
      -Command @("az", "account", "show", "--query", "id", "-o", "tsv") `
      -SuccessMessage "Azure login verified."
    if ($currentSubscription -ne $SubscriptionId) {
        Write-Error "Logged in to wrong subscription ($currentSubscription vs $SubscriptionId)."
        exit 1
    }
    if (-not $AppServiceName -or -not $ResourceGroup) {
        Write-Error "AZURE_APP_SERVICE or AZURE_RESOURCE_GROUP not set."
        exit 1
    }

    # — Package backend —
    Run-Command `
      -Command @("azd", "package", "backend", "--output-path", $tempPackageFile) `
      -SuccessMessage "Application packaged to '$tempPackageFile'."
    $PackagePath = $tempPackageFile

    # — Check/Create slot —
    $slotExists = Run-Command `
      -Command @("az", "webapp", "deployment", "slot", "list", `
                 "--resource-group", $ResourceGroup, `
                 "--name", $AppServiceName, `
                 "--query", "[?name=='$SlotName']", "-o", "tsv") `
      -SuccessMessage "Checked for existing slot '$SlotName'."

    if ([string]::IsNullOrEmpty($slotExists)) {
        Write-Host "Slot $SlotName does not yet exist. Creating it ..."
        Run-Command `
          -Command @("az", "webapp", "deployment", "slot", "create", `
                     "--name", $AppServiceName, `
                     "--resource-group", $ResourceGroup, `
                     "--slot", $SlotName, `
                     "--configuration-source", $AppServiceName, `
                     "--output", "none") `
          -SuccessMessage "Slot '$SlotName' created."

        Run-Command `
          -Command @("az", "webapp", "identity", "assign", `
                     "--name", $AppServiceName, `
                     "--resource-group", $ResourceGroup, `
                     "--slot", $SlotName, `
                     "--output", "none") `
          -SuccessMessage "Managed identity enabled for slot."

        $slotPrincipalId = Run-Command `
          -Command @("az", "webapp", "identity", "show", `
                     "--name", $AppServiceName, `
                     "--resource-group", $ResourceGroup, `
                     "--slot", $SlotName, `
                     "--query", "principalId", `
                     "-o", "tsv") `
          -SuccessMessage "Retrieved slot principal ID."

        # — RBAC role assignments with retry —
        Write-Host "Assigning RBAC roles..."
        $roles = @(
          "1407120a-92aa-4202-b7e9-c0e197c71c8f",
          "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd",
          "f2dc8367-1007-4938-bd23-fe263f013447",
          "2a2b9908-6ea1-4ae2-8e65-a410df84e7d1",
          "acdd72a7-3385-48ef-bd42-f606fba81ae7"
        )
        foreach ($roleId in $roles) {
            $attempt = 0; $maxRetries = 3; $assigned = $false
            while (-not $assigned -and $attempt -lt $maxRetries) {
                $out = & az role assignment create `
                       --assignee $slotPrincipalId `
                       --role       $roleId `
                       --scope      "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup" `
                       --output     none 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "Role $roleId assigned."
                    $assigned = $true
                }
                elseif ($out -match "Cannot find user or service principal in graph database") {
                    $attempt++
                    Write-Warning "Graph not ready; retrying ($attempt/$maxRetries) in 10s..."
                    Start-Sleep -Seconds 10
                }
                else {
                    Write-Error "Error assigning role ${roleId}: ${out}"
                    exit 1
                }
            }
            if (-not $assigned) {
                Write-Error "Failed to assign role ${roleId} after $maxRetries attempts."
                exit 1
            }
        }

        # — Cosmos DB role (if configured) —
        if ($env:AZURE_COSMOSDB_ACCOUNT -and $env:USE_CHAT_HISTORY_COSMOS -eq "true") {
            $cosmosRg    = $env:AZURE_COSMOSDB_RESOURCE_GROUP ?? $ResourceGroup
            $cosmosScope = Run-Command `
              -Command @("az", "cosmosdb", "show", `
                         "--resource-group", $cosmosRg, `
                         "--name", $env:AZURE_COSMOSDB_ACCOUNT, `
                         "--query", "id", "-o", "tsv") `
              -SuccessMessage "Retrieved Cosmos DB scope."
            Run-Command `
              -Command @("az", "cosmosdb", "sql", "role", "assignment", "create", `
                         "--resource-group", $cosmosRg, `
                         "--account-name", $env:AZURE_COSMOSDB_ACCOUNT, `
                         "--role-definition-id", "$cosmosScope/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002", `
                         "--principal-id", $slotPrincipalId, `
                         "--scope", $cosmosScope, `
                         "--output", "none") `
              -SuccessMessage "Cosmos DB Data Contributor role assigned."
        }
        else {
            Write-Host "Skipping Cosmos DB role assignment."
        }
        Write-Host "Slot $SlotName was successfully created and assigned system-managed PrincipalId $slotPrincipalId."
        Write-Host "All necessary Azure roles were assigned."
    }
    else {
        Write-Host "Slot '$SlotName' already exists."
    }

    # — Deploy —

    Write-Host "Deploying to slot. This step might take a couple of minutes."
    Run-Command `
      -Command @("az", "webapp", "deploy", `
                 "--resource-group", $ResourceGroup, `
                 "--name",         $AppServiceName, `
                 "--src-path",     $PackagePath, `
                 "--slot",         $SlotName, `
                 "--type",         "zip", `
                 "--track-status", "false", `
                 "--output",       "none") `
      -SuccessMessage "Deployment to '$SlotName' initiated."

    # — Startup file —
    Run-Command `
      -Command @("az", "webapp", "config", "set", `
                 "--startup-file", "python3 -m gunicorn main:app", `
                 "--name",         $AppServiceName, `
                 "--resource-group", $ResourceGroup, `
                 "--slot",          $SlotName, `
                 "--output",        "none") `
      -SuccessMessage "Startup command configured."

    # — App settings —
    $settings = @()
    foreach ($line in $azdEnv) {
        if ($line -match "([^=]+)=(.*)") {
            $settings += [pscustomobject]@{
              name        = $matches[1]
              value       = $matches[2] -replace '^"|"$'
              slotSetting = $false
            }
        }
    }
    $settings += [pscustomobject]@{ name="WEBSITE_WEBDEPLOY_USE_SCM"; value="false"; slotSetting=$false }
    $settings | ConvertTo-Json | Out-File -FilePath $tempJsonFile -Encoding utf8

    Run-Command `
      -Command @("az", "webapp", "config", "appsettings", "set", `
                 "--resource-group", $ResourceGroup, `
                 "--name",          $AppServiceName, `
                 "--slot",          $SlotName, `
                 "--settings",      "@$tempJsonFile", `
                 "--output",        "none") `
      -SuccessMessage "App settings applied."

    Write-Host "---------------------------------------------------------------"
    Write-Host "✅ Successfully deployed to slot '$SlotName'."
    Write-Host "---------------------------------------------------------------"
}
catch {
    Write-Error "Unexpected error: $($_.Exception.Message)"
    exit 1
}
finally {
    if (Test-Path $tempJsonFile)    { Remove-Item $tempJsonFile    -Force -ErrorAction SilentlyContinue }
    if (Test-Path $tempPackageFile) { Remove-Item $tempPackageFile -Force -ErrorAction SilentlyContinue }
}