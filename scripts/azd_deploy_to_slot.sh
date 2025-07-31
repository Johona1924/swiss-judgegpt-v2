#!/usr/bin/env bash
set -euo pipefail

# Ensure we clean up temp files on exit
cleanup() {
  [[ -f "${tempJsonFile:-}" ]]    && rm -f "$tempJsonFile"
  [[ -f "${tempPackageFile:-}" ]] && rm -f "$tempPackageFile"
  echo "Cleaned up all temporary files."
}
trap cleanup EXIT

# Catch any unexpected error
catch_errors() {
  echo "Unexpected error: $BASH_COMMAND" >&2
  exit 1
}
trap 'catch_errors' ERR

# Check for required parameter
if [ $# -ne 1 ]; then
  echo "Usage: $0 <SlotName>"
  exit 1
fi
SlotName="$1"

# Helper: run a CLI command, print success or exit on error
run_command() {
  local success_message="$1"; shift
  local output
  if ! output=$("$@" 2>&1); then
    echo "$output" >&2
    exit 1
  fi
  echo "$success_message" >&2
  echo "$output"
}

# Create temp files
tempJsonFile=$(mktemp /tmp/XXXXXXXX.json)
tempPackageFile=$(mktemp /tmp/XXXXXXXX.zip)

# — Set working directory —
cd "$(dirname "$0")/.." 
echo "Working directory set to project root."

# — Load azd environment —
azdEnv=$(run_command "Loaded azd environment variables." azd env get-values)

# Parse and export each AZD env var
declare -A _azd_env
while IFS= read -r line; do
  if [[ "$line" =~ ^([^=]+)=(.*)$ ]]; then
    key="${BASH_REMATCH[1]}"
    value="${BASH_REMATCH[2]}"
    value="${value%\"}"; value="${value#\"}"
    export "$key"="$value"
    _azd_env["$key"]="$value"
  fi
done <<< "$azdEnv"

# — Gather basic info —
azdEnvName="$AZURE_ENV_NAME"
gitBranchName=$(git rev-parse --abbrev-ref HEAD | xargs)
ResourceGroup="$AZURE_RESOURCE_GROUP"
AppServiceName="$AZURE_APP_SERVICE"
SubscriptionId="$AZURE_SUBSCRIPTION_ID"
SubscriptionName=$(run_command \
  "Retrieved Azure subscription name." \
  az account show --subscription "$SubscriptionId" --query name -o tsv)

# — Confirm with user —
cat <<EOF
Please confirm the following deployment details:
- Azd Environment:  $azdEnvName
- Git Branch:       $gitBranchName
- Subscription:     $SubscriptionName ($SubscriptionId)
- Resource Group:   $ResourceGroup
- App Service:      $AppServiceName
- Target Slot:      $SlotName

Proceed? (y/n)
EOF
read -r confirm
if [ "$confirm" != "y" ]; then
  echo "Deployment cancelled by user."
  exit 0
fi

# — Validate login & subscription —
currentSubscription=$(run_command \
  "Azure login verified." \
  az account show --query id -o tsv)
if [ "$currentSubscription" != "$SubscriptionId" ]; then
  echo "Logged in to wrong subscription ($currentSubscription vs $SubscriptionId)." >&2
  exit 1
fi
if [ -z "$AppServiceName" ] || [ -z "$ResourceGroup" ]; then
  echo "AZURE_APP_SERVICE or AZURE_RESOURCE_GROUP not set." >&2
  exit 1
fi

# — Package backend —
run_command \
  "Application packaged to '$tempPackageFile'." \
  azd package backend --output-path "$tempPackageFile"
PackagePath="$tempPackageFile"

# — Check/Create slot —
slotExists=$(run_command \
  "Checked for existing slot '$SlotName'." \
  az webapp deployment slot list \
    --resource-group "$ResourceGroup" \
    --name "$AppServiceName" \
    --query "[?name=='$SlotName']" -o tsv)

if [ -z "$slotExists" ]; then
  echo "Slot $SlotName does not yet exist. Creating it ..."
  run_command \
    "Slot '$SlotName' created." \
    az webapp deployment slot create \
      --name "$AppServiceName" \
      --resource-group "$ResourceGroup" \
      --slot "$SlotName" \
      --configuration-source "$AppServiceName" \
      --output none

  run_command \
    "Managed identity enabled for slot." \
    az webapp identity assign \
      --name "$AppServiceName" \
      --resource-group "$ResourceGroup" \
      --slot "$SlotName" \
      --output none

  slotPrincipalId=$(run_command \
    "Retrieved slot principal ID." \
    az webapp identity show \
      --name "$AppServiceName" \
      --resource-group "$ResourceGroup" \
      --slot "$SlotName" \
      --query principalId -o tsv)

  echo "Assigning RBAC roles..."
  roles=(
    1407120a-92aa-4202-b7e9-c0e197c71c8f
    5e0bd9bd-7b93-4f28-af87-19fc36ad61bd
    f2dc8367-1007-4938-bd23-fe263f013447
    2a2b9908-6ea1-4ae2-8e65-a410df84e7d1
    acdd72a7-3385-48ef-bd42-f606fba81ae7
  )
  for roleId in "${roles[@]}"; do
    attempt=0; maxRetries=3; assigned=false
    while [ "$assigned" = false ] && [ "$attempt" -lt "$maxRetries" ]; do
      out=$(MSYS_NO_PATHCONV=1 az role assignment create \
            --assignee "$slotPrincipalId" \
            --role "$roleId" \
            --scope "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup" \
            --subscription      "$SubscriptionId" \
            --output none 2>&1) && rc=0 || rc=$?
      if [ "$rc" -eq 0 ]; then
        echo "Role $roleId assigned."
        assigned=true
      elif [[ "$out" =~ "Cannot find user or service principal in graph database" ]]; then
        attempt=$((attempt+1))
        echo "Graph not ready; retrying ($attempt/$maxRetries) in 10s..." >&2
        sleep 10
      else
        echo "Error assigning role ${roleId}: ${out}" >&2
        exit 1
      fi
    done
    if [ "$assigned" != true ]; then
      echo "Failed to assign role ${roleId} after $maxRetries attempts." >&2
      exit 1
    fi
  done

  # — Cosmos DB role (if configured) —
  if [ -n "${AZURE_COSMOSDB_ACCOUNT:-}" ] && [ "${USE_CHAT_HISTORY_COSMOS:-}" = "true" ]; then
    cosmosRg="${AZURE_COSMOSDB_RESOURCE_GROUP:-$ResourceGroup}"
    cosmosScope=$(run_command \
      "Retrieved Cosmos DB scope." \
      az cosmosdb show \
        --resource-group "$cosmosRg" \
        --name "$AZURE_COSMOSDB_ACCOUNT" \
        --query id -o tsv)
    MSYS_NO_PATHCONV=1 run_command \
      "Cosmos DB Data Contributor role assigned." \
      az cosmosdb sql role assignment create \
        --resource-group "$cosmosRg" \
        --account-name "$AZURE_COSMOSDB_ACCOUNT" \
        --role-definition-id "$cosmosScope/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002" \
        --principal-id "$slotPrincipalId" \
        --subscription      "$SubscriptionId" \
        --scope "$cosmosScope" \
        --output none
  else
    echo "Skipping Cosmos DB role assignment."
  fi

  echo "Slot $SlotName was successfully created and assigned system-managed PrincipalId $slotPrincipalId."
  echo "All necessary Azure roles were assigned."
else
  echo "Slot '$SlotName' already exists."
fi

# — Deploy —
echo "Deploying to slot. This step might take a couple of minutes."
run_command \
  "Deployment to '$SlotName' initiated." \
  az webapp deploy \
    --resource-group "$ResourceGroup" \
    --name "$AppServiceName" \
    --src-path "$PackagePath" \
    --slot "$SlotName" \
    --type zip \
    --track-status false \
    --output none

# — Startup file —
run_command \
  "Startup command configured." \
  az webapp config set \
    --startup-file "python3 -m gunicorn main:app" \
    --name "$AppServiceName" \
    --resource-group "$ResourceGroup" \
    --slot "$SlotName" \
    --output none

# — App settings —
# Build JSON array of settings
json="["
first=true
for key in "${!_azd_env[@]}"; do
  val=${_azd_env[$key]}
  if $first; then first=false; else json+=","; fi
  json+=$'\n  '"{\"name\":\"$key\",\"value\":\"$val\",\"slotSetting\":false}"
done
json+=$',\n  {"name":"WEBSITE_WEBDEPLOY_USE_SCM","value":"false","slotSetting":false}\n]'
echo -e "$json" > "$tempJsonFile"

run_command \
  "App settings applied." \
  az webapp config appsettings set \
    --resource-group "$ResourceGroup" \
    --name "$AppServiceName" \
    --slot "$SlotName" \
    --settings "@$tempJsonFile" \
    --output none

echo "---------------------------------------------------------------"
echo "✅ Successfully deployed to slot '$SlotName'."
echo "---------------------------------------------------------------"