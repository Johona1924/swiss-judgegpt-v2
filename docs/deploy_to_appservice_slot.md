# Deploying to App Service Deployment Slots

This guide covers deploying the application to Azure App Service deployment slots using the automated PowerShell or shell scripts.

## Overview

The `azd_deploy_to_slot.ps1` or `azd_deploy_to_slot.sh` script automate the deployment of the application to Azure App Service deployment slots. 

## What the Script Does

The deployment script performs the following operations:

1. **Environment Validation**: Loads azd environment variables and validates Azure login status
2. **User Confirmation**: Displays deployment details for confirmation before proceeding
3. **Application Packaging**: Uses `azd package` to create a deployment-ready zip file
4. **Slot Management**: Creates the deployment slot if it doesn't exist, copying configuration from production
5. **Identity Configuration**: Assigns system managed identity to the new slot
6. **RBAC Role Assignment**: Grants required Azure roles to the slot's managed identity
7. **Application Deployment**: Deploys the packaged application to the target slot
8. **Configuration Update**: Sets application settings and startup configuration for the slot

## Assigned Azure Roles

The script automatically assigns the following roles to the slot's managed identity (with role definition IDs):

- **Search Index Data Reader** (`1407120a-92aa-4202-b7e9-c0e197c71c8f`): Access to Azure AI Search indexes
- **Cognitive Services OpenAI User** (`5e0bd9bd-7b93-4f28-af87-19fc36ad61bd`): Access to Azure OpenAI services
- **Cognitive Services Speech User** (`f2dc8367-1007-4938-bd23-fe263f013447`): Access to speech services
- **Storage Blob Data Reader** (`2a2b9908-6ea1-4ae2-8e65-a410df84e7d1`): Read access to Azure Storage blobs
- **Reader** (`acdd72a7-3385-48ef-bd42-f606fba81ae7`): General read access to resources
- **Cosmos DB Built-in Data Contributor** (`00000000-0000-0000-0000-000000000002`): Access to Cosmos DB (only if `USE_CHAT_HISTORY_COSMOS=true` and `AZURE_COSMOSDB_ACCOUNT` is configured)

Role assignments are created at the resource group scope, with retry logic for Azure AD propagation delays.

### Application Settings Source
App settings are derived from the currently selected azd environment variables (obtained via `azd env get-values`). This includes all environment variables from the active azd environment's `.env` file, plus the `WEBSITE_WEBDEPLOY_USE_SCM=false` setting.

### Startup Configuration
The script sets the startup command to `python3 -m gunicorn main:app`, which is the standard startup command for Python web applications as documented in the main README.md.

## Prerequisites

- **Azure CLI**: The script requires the Azure CLI (`az`) to be installed and available in the PATH
- **Azure Developer CLI**: Must have `azd` installed with a configured environment
- **PowerShell 7+**: Required for script execution (Windows users)

## Usage

```powershell
.\scripts\azd_deploy_to_slot.ps1 -SlotName "staging"
```

The script operates on the currently active azd environment. Switch environments using `azd env select` if needed.

## Required Azure Permissions (NOT CONFIRMED YET)

To run this script successfully, your Azure account needs the following permissions:

- **Contributor** role on the Resource Group (to create/manage App Service slots)
- **Role Based Access Control Administrator** role on the Resource Group (to assign RBAC roles)
- **Azure Service Deploy** permissions on the App Service
- **Cosmos DB Account Contributor** (if `AZURE_USE_COSMOS_DB=true` in environment variables)

## Post-Deployment Configuration

When a new slot is created, settings are copied from production. Manual configuration changes are required:

### Authentication Settings
In the Azure Portal, go to the newly created slot, and go to ...
- ... Settings -> Authentication : Change the App (client) ID to the ID provided by your Authentication provided (e.g. Auth0). This step is necessary because the ID is by default copied from the production slot during slot creation.
- ... Settings -> Environment Variables : Create or update the `auth0_AUTHENTICATION_SECRET`environment variable with the App Secret value provided by your Authentication provider (e.g. Auth0). Ensure the authentication secret is marked as a deployment slot setting (check the slot setting option).
- Go back to Settings -> Authentication -> Edit, and make sure `Client secret setting name` is set to `auth0_AUTHENTICATION_SECRET`.

### Application Restart
Restart the app service slot to apply all configuration changes.

## Details

This script is a workaround for deploying directly to a specific App Service slot, as this is not natively supported by the Azure Developer CLI (`azd`). Normally, the app is provisioned and deployed using `azd up` (for full infrastructure provisioning and deployment) or `azd deploy` (for code-only changes), as described in the main README.md. However, these commands do not support targeting a specific deployment slot.

### Packaging Process
The script packages the application code by invoking `azd package backend --output-path <zipfile>`. The `backend` service name is defined in your `azure.yaml` file and refers to the backend application. This ensures the same build and packaging logic as the standard azd workflow is used.

### Deployment Method
After packaging, the script deploys the zip file to the specified App Service slot using the Azure CLI command:

```
az webapp deploy --resource-group <ResourceGroup> --name <AppServiceName> --src-path <PackagePath> --slot <SlotName> --type zip --track-status false
```
This method uploads and deploys the packaged application directly to the chosen slot, bypassing the default azd deployment flow.

## Troubleshooting

- Ensure you're logged into the correct Azure subscription before running the script
- Verify that the azd environment is properly configured with `azd env get-values`
- Check that all required environment variables are set (AZURE_APP_SERVICE, AZURE_RESOURCE_GROUP, AZURE_SUBSCRIPTION_ID, etc.)
- Ensure Azure CLI (`az`) is installed and authenticated
- Allow time for Azure role propagation if you encounter permission errors immediately after slot creation
- For Cosmos DB role assignment issues, verify that `USE_CHAT_HISTORY_COSMOS=true` and `AZURE_COSMOSDB_ACCOUNT` are set in your azd environment

