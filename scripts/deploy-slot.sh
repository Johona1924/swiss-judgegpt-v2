#!/bin/bash
set -e

# Switch to the project root directory
cd "$(dirname "$0")/.."

echo "Loading environment variables from azd env"
eval "$(azd env get-values)"

echo "Checking Azure login and subscription..."
CURRENT_SUBSCRIPTION=$(az account show --query "id" -o tsv 2>/dev/null)

if [ -z "$CURRENT_SUBSCRIPTION" ]; then
  echo "You are not logged into Azure. Please run 'az login' and try again." >&2
  exit 1
fi

if [ "$CURRENT_SUBSCRIPTION" != "$AZURE_SUBSCRIPTION_ID" ]; then
  echo "Logged in to wrong Azure subscription. Please run 'az account set --subscription $AZURE_SUBSCRIPTION_ID'." >&2
  exit 1
fi
echo "Azure login and subscription are valid."

# Ensure required environment variables are set
if [ -z "$AZURE_APP_SERVICE_SLOT_NAME" ]; then
    echo "Deploy-to-slot hook requires AZURE_APP_SERVICE_SLOT_NAME environment variable to be set." >&2
    exit 1
fi

SLOT_NAME=$AZURE_APP_SERVICE_SLOT_NAME

if [ -z "$AZURE_APP_SERVICE" ] || [ -z "$AZURE_RESOURCE_GROUP" ]; then
    echo "AZURE_APP_SERVICE or AZURE_RESOURCE_GROUP environment variables not set. Make sure you have run 'azd provision'." >&2
    exit 1
fi

# Check if the slot exists
echo "Checking if slot '$SLOT_NAME' exists..."
SLOT_EXISTS=$(az webapp deployment slot list --resource-group "$AZURE_RESOURCE_GROUP" --name "$AZURE_APP_SERVICE" --query "[?name=='$SLOT_NAME']" -o tsv)

if [ -z "$SLOT_EXISTS" ]; then
  echo "Slot '$SLOT_NAME' does not exist. Creating it..."
  az webapp deployment slot create --name "$AZURE_APP_SERVICE" --resource-group "$AZURE_RESOURCE_GROUP" --slot "$SLOT_NAME" --configuration-source "$AZURE_APP_SERVICE"
  if [ $? -ne 0 ]; then
    echo "Failed to create deployment slot." >&2
    exit 1
  fi
  echo "Slot '$SLOT_NAME' created successfully."
else
  echo "Slot '$SLOT_NAME' already exists."
fi

# Build the frontend
echo "Building frontend..."
(cd app/frontend && npm install && npm run build)

# Create the deployment package
echo "Creating deployment package..."
(cd app && zip -r ../deployment.zip .)

# Deploy to the slot
echo "Deploying to slot '$SLOT_NAME' of app '$AZURE_APP_SERVICE' in resource group '$AZURE_RESOURCE_GROUP'..."
az webapp deployment source config-zip \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$AZURE_APP_SERVICE" \
  --slot "$SLOT_NAME" \
  --src "deployment.zip" \
  --timeout 900

# Clean up
echo "Cleaning up..."
rm deployment.zip

echo "Deployment to slot '$SLOT_NAME' completed."