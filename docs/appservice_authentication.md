# Azure App Service Built-in Authentication for Chat History

This document describes how to use Azure App Service's built-in authentication and authorization feature with CosmosDB chat history, instead of Microsoft Entra ID authentication.

## Overview

Azure App Service provides built-in authentication and authorization capabilities that work with various identity providers (Auth0, Microsoft Entra ID, Google, Facebook, etc.). This approach simplifies authentication by letting Azure App Service handle the authentication flow and user identity extraction, while your application focuses on business logic.

## Environment Variables

### Required for App Service Authentication

- `USE_APPSERVICE_AUTHENTICATION=true` - Enables Azure App Service built-in authentication

### Validation Rules

1. `AZURE_USE_AUTHENTICATION` and `USE_APPSERVICE_AUTHENTICATION` cannot both be `true`
2. `USE_CHAT_HISTORY_COSMOS=true` requires either `AZURE_USE_AUTHENTICATION=true` OR `USE_APPSERVICE_AUTHENTICATION=true`

## Setup Instructions

1. **Configure Environment Variables**
   ```bash
   azd env set USE_APPSERVICE_AUTHENTICATION true
   azd env set USE_CHAT_HISTORY_COSMOS true
   azd env set AZURE_USE_AUTHENTICATION false
   ```

2. **Deploy the Application**
   ```bash
   azd up
   ```

3. **Configure App Service Authentication**
   - In the Azure portal, navigate to your App Service
   - Go to "Authentication" in the left sidebar
   - Configure your preferred identity provider (Auth0, Microsoft Entra ID, Google, etc.)

## Authentication Workflow

### When Deployed on Azure App Service with Authentication Enabled

1. **User Authentication**: Users authenticate through the configured identity provider
2. **Header Injection**: Azure App Service injects authentication headers into every request:
   - `X-Ms-Client-Principal-Id`: Unique user identifier
   - `X-Ms-Client-Principal-Name`: User's display name
   - `X-Ms-Client-Principal-Idp`: Identity provider name
   - `X-Ms-Client-Principal`: Base64-encoded user claims
3. **User Identification**: Application extracts `X-Ms-Client-Principal-Id` as the unique user ID (stored as `user_principal_id` or `oid`). For auth0 identity provider, an example is auth0|507f1f77bcf86cd799439011.
4. **Chat History Storage**: User ID is used as the partition key for CosmosDB chat history

### When Running Locally (Development Mode)

When running locally without App Service authentication:
- No authentication headers are present in requests
- Application falls back to a sample user for development purposes
- Sample user has predefined headers including `X-Ms-Client-Principal-Id`
- `oid` is set to "00000000-0000-0000-0000-000000000000"
- This allows testing chat history functionality during local development

## Key Implementation Details

### Headers Used

The application relies on these Azure App Service authentication headers:
- **`X-Ms-Client-Principal-Id`**: Primary user identifier (required)
- **`X-Ms-Client-Principal-Name`**: User display name
- **`X-Ms-Client-Principal-Idp`**: Identity provider (e.g., "aad", "google", "auth0")

### Chat History Storage

- **User Isolation**: Each user's chat history is isolated using their `X-Ms-Client-Principal-Id`
- **CosmosDB Partitioning**: Uses user ID as partition key for optimal performance
- **Session Management**: Chat sessions and messages are stored with user-specific identifiers

## Security Considerations

- **No Document-Level Access Control**: This mode does not implement search document access control
- **User Isolation**: Chat history is completely isolated between users
- **Authentication Required**: All chat history operations require valid authentication headers
- **Header Security**: App Service ensures authentication headers cannot be spoofed by external requests

## Differences from Microsoft Entra Authentication

| Feature | Microsoft Entra | App Service Authentication |
|---------|----------------|---------------------------|
| Identity Provider | Microsoft Entra ID only | Any supported provider |
| Application Registration | Required | Not Required |
| Document Access Control | Supported | Not Supported |
| Chat History | Supported | Supported |
| User Upload | Supported | Untested |
| Local Development | Token-based | Sample user fallback |

## Troubleshooting

### Common Issues

1. **Both Auth Methods Enabled**
   - Error: "AZURE_USE_AUTHENTICATION and USE_APPSERVICE_AUTHENTICATION cannot both be true"
   - Solution: Set only one authentication method to `true`

2. **Chat History Without Authentication**
   - Error: "USE_CHAT_HISTORY_COSMOS requires either authentication method"
   - Solution: Enable either `AZURE_USE_AUTHENTICATION` or `USE_APPSERVICE_AUTHENTICATION`

3. **Missing User ID in Production**
   - Untested behavior, probably will fall back to sample user as well.
   - TODO : Implement error handling that differentiates between production and local development (see below).

4. **Local Development Issues**
   - Issue: No authentication headers when running locally
   - Expected: Application uses sample user with predefined headers for development

