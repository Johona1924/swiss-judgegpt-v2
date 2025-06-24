#!/bin/bash
set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <slot-name>"
  exit 1
fi

SLOT_NAME=$1

# Switch to the project root directory
cd "$(dirname "$0")/.."

echo "Loading environment variables from azd env"
eval "$(azd env get-values)"

if [ -z "$AZURE_APP_SERVICE" ] || [ -z "$AZURE_RESOURCE_GROUP" ]; then
    echo "AZURE_APP_SERVICE or AZURE_RESOURCE_GROUP environment variable not set. Make sure you have run 'azd provision'."
    exit 1
fi

echo "Checking if slot '$SLOT_NAME' exists..."
SLOT_EXISTS=$(az webapp deployment slot list --resource-group "$AZURE_RESOURCE_GROUP" --name "$AZURE_APP_SERVICE" --query "[?name=='$SLOT_NAME']" -o tsv)

if [ -z "$SLOT_EXISTS" ]; then
  echo "Slot '$SLOT_NAME' does not exist. Creating it..."
  az webapp deployment slot create --name "$AZURE_APP_SERVICE" --resource-group "$AZURE_RESOURCE_GROUP" --slot "$SLOT_NAME" --configuration-source "$AZURE_APP_SERVICE"
  echo "Slot '$SLOT_NAME' created successfully."
else
  echo "Slot '$SLOT_NAME' already exists."
fi

echo "Building frontend..."
(cd app/frontend && npm install && npm run build)

echo "Creating deployment package..."
(cd app && zip -r ../deployment.zip .)

echo "Deploying to slot '$SLOT_NAME' of app '$AZURE_APP_SERVICE' in resource group '$AZURE_RESOURCE_GROUP'..."
az webapp deployment source config-zip \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$AZURE_APP_SERVICE" \
  --slot "$SLOT_NAME" \
  --src "deployment.zip" \
  --timeout 900

echo "Cleaning up..."
rm deployment.zip

echo "Deployment to slot '$SLOT_NAME' completed."