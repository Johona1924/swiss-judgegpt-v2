#!/bin/bash
set -e

# --- Cleanup ---
cleanup() {
    echo "Cleaning up temporary files..."
    if [[ -n "$tempJsonFile" && -f "$tempJsonFile" ]]; then
        rm -f "$tempJsonFile"
    fi
    if [[ -n "$tempPackageFile" && -f "$tempPackageFile" ]]; then
        rm -f "$tempPackageFile"
    fi
}
trap cleanup EXIT

# --- Script Start ---
if [ -z "$1" ]; then
    echo "Error: The name of the deployment slot is required."
    echo "Usage: $0 <SlotName>"
    exit 1
fi

SlotName=$1

# Create temporary files
tempJsonFile=$(mktemp)
tempPackageFile=$(mktemp -u).zip

# Set working directory to project root
cd "$(dirname "$0")/.."

# --- Load Environment and Gather Information ---
echo "Loading azd environment variables..."
while IFS='=' read -r key value; do
    # remove quotes from value
    value="${value%\"}"
    value="${value#\"}"
    export "$key"="$value"
done <<< "$(azd env get-values)"

azdEnvName=$AZURE_ENV_NAME
gitBranchName=$(git rev-parse --abbrev-ref HEAD | tr -d '[:space:]')
ResourceGroup=$AZURE_RESOURCE_GROUP
AppServiceName=$AZURE_APP_SERVICE
SubscriptionId=$AZURE_SUBSCRIPTION_ID
SubscriptionName=$(az account show --subscription "$SubscriptionId" --query "name" -o tsv)

# --- User Confirmation ---
echo "Please confirm the following deployment details:"
echo "- Azd Environment:  $azdEnvName"
echo "- Git Branch:       $gitBranchName"
echo "- Subscription:     $SubscriptionName ($SubscriptionId)"
echo "- Resource Group:   $ResourceGroup"
echo "- App Service:      $AppServiceName"
echo "- Target Slot:      $SlotName"
echo ""
read -p "Are you sure you want to proceed with the deployment? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled by user."
    exit 0
fi

# --- Validate Environment ---
echo "Checking Azure login and subscription..."
currentSubscription=$(az account show --query "id" -o tsv)
if [ $? -ne 0 ]; then
    echo "Error: You are not logged into Azure. Please run 'az login' and try again." >&2
    exit 1
fi
if [ "$currentSubscription" != "$SubscriptionId" ]; then
    echo "Error: Logged in to wrong Azure subscription. Please run 'az account set --subscription $SubscriptionId'." >&2
    exit 1
fi
echo "Azure login and subscription are valid."

if [ -z "$AppServiceName" ] || [ -z "$ResourceGroup" ]; then
    echo "Error: AZURE_APP_SERVICE or AZURE_RESOURCE_GROUP environment variables not set. Make sure you have run 'azd provision'." >&2
    exit 1
fi

# --- Package Application ---
echo "Packaging service backend..."
azd package backend --output-path "$tempPackageFile"
if [ $? -ne 0 ]; then
    echo "Error: Failed to package the application. Aborting." >&2
    exit 1
fi
PackagePath=$tempPackageFile
echo "Application packaged successfully to '$PackagePath'."

# --- Check/Create Deployment Slot ---
echo "Checking if slot '$SlotName' exists..."
slotExists=$(az webapp deployment slot list --resource-group "$ResourceGroup" --name "$AppServiceName" --query "[?name=='$SlotName']" -o tsv)
if [ -z "$slotExists" ]; then
    echo "Slot '$SlotName' does not exist. Creating it..."
    az webapp deployment slot create --name "$AppServiceName" --resource-group "$ResourceGroup" --slot "$SlotName" --configuration-source "$AppServiceName"
    if [ $? -ne 0 ]; then
        echo "Error: Failed to create deployment slot." >&2
        exit 1
    fi
    echo "Slot '$SlotName' created successfully."
else
    echo "Slot '$SlotName' already exists."
fi

# --- Deploy to Slot ---
echo "Deploying to slot '$SlotName' in AppService '$AppServiceName'..."
az webapp deploy --resource-group "$ResourceGroup" --name "$AppServiceName" --src-path "$PackagePath" --slot "$SlotName" --type zip --track-status false
if [ $? -ne 0 ]; then
    echo "Error: Failed to deploy webapp to slot." >&2
    exit 1
fi
echo "Deployment to slot initiated. App service will build the package in the background."

# --- Configure Slot Settings ---
echo "Updating app configuration and app settings for slot '$SlotName'..."
az webapp config set --startup-file "python3 -m gunicorn main:app" --name "$AppServiceName" --resource-group "$ResourceGroup" --slot "$SlotName"
if [ $? -ne 0 ]; then
    echo "Error: Failed to set startup file." >&2
    exit 1
fi

# Create a JSON file with all environment variables plus the SCM setting
json_settings="["
first=true
while IFS='=' read -r key value; do
    if [ "$first" = false ]; then
        json_settings+=","
    fi
    # remove quotes from value
    value="${value%\"}"
    value="${value#\"}"
    # escape backslashes and double quotes in value for JSON
    value_escaped=$(echo "$value" | sed -e 's/\/\\/g' -e 's/"/\"/g')
    json_settings+=$(printf '{"name":"%s","value":"%s","slotSetting":false}' "$key" "$value_escaped")
    first=false
done <<< "$(azd env get-values)"

if [ "$first" = false ]; then
    json_settings+=","
fi
json_settings+=$(printf '{"name":"WEBSITE_WEBDEPLOY_USE_SCM","value":"false","slotSetting":false}')
json_settings+="]"

echo "$json_settings" > "$tempJsonFile"

az webapp config appsettings set --resource-group "$ResourceGroup" --name "$AppServiceName" --slot "$SlotName" --settings "@$tempJsonFile"
if [ $? -ne 0 ]; then
    echo "Error: Failed to set app settings from JSON file." >&2
    exit 1
fi
echo "Successfully updated app configuration and settings."

# --- Final Success Message ---
echo "------------------------------------------------------------------"
echo "✅ Successfully deployed to slot '$SlotName'."
echo "------------------------------------------------------------------"

exit 0
