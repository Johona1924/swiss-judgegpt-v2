# Auth0 Integration for Chat History

This document describes how to set up and use Auth0 authentication with CosmosDB chat history instead of Microsoft Entra ID.

## Overview

The application now supports Auth0 as an alternative authentication provider for chat history functionality. This bypasses the requirement for Microsoft Entra application registration and management permissions.

## Environment Variables

### Required for Auth0 Integration

- `USE_AUTH0_AUTHENTICATION=true` - Enables Auth0 authentication
- `USE_CHAT_HISTORY_COSMOS=true` - Enables CosmosDB chat history storage

### Validation Rules

1. `AZURE_USE_AUTHENTICATION` and `USE_AUTH0_AUTHENTICATION` cannot both be `true`
2. `USE_CHAT_HISTORY_COSMOS=true` requires either `AZURE_USE_AUTHENTICATION=true` OR `USE_AUTH0_AUTHENTICATION=true`

## Setup Instructions

1. **Configure Environment Variables**
   ```bash
   azd env set USE_AUTH0_AUTHENTICATION true
   azd env set USE_CHAT_HISTORY_COSMOS true
   azd env set AZURE_USE_AUTHENTICATION false
   ```

2. **Deploy the Application**
   ```bash
   azd up
   ```

## Implementation Details

### Authentication Flow

1. **Auth0 Headers**: The application expects Auth0 to pass user identity in request headers after authentication
2. **User Identification**: Uses `user_principal_id` from Auth0 headers as the unique user identifier
3. **Chat History**: Stores chat sessions and messages in CosmosDB with the Auth0 user ID

### Key Components

- **authentication_auth0_helper.py**: Main Auth0 authentication helper class
- **authentication_auth0.py**: Utility functions for extracting user details from Auth0 headers
- **cosmosdb.py**: Chat history storage using Auth0 user IDs

### Infrastructure Changes

- CosmosDB resources are provisioned when `(useAuthentication || useAuth0Authentication) && useChatHistoryCosmos`
- No Microsoft Entra applications are created when `USE_AUTH0_AUTHENTICATION=true`
- Auth update scripts skip Microsoft Entra operations for Auth0 authentication

## Security Considerations

- **No Access Control**: Auth0 mode does not implement document-level access control
- **User Isolation**: Chat history is isolated by Auth0 user ID
- **Authentication Required**: All chat history operations require valid Auth0 authentication

## Differences from Microsoft Entra

| Feature | Microsoft Entra | Auth0 |
|---------|----------------|-------|
| Application Registration | Required | Not Required |
| Document Access Control | Supported | Not Supported |
| Chat History | Supported | Supported |
| User Upload | Supported | Supported |
| Admin Permissions | Required | Not Required |

## Troubleshooting

### Common Issues

1. **Both Auth Methods Enabled**
   - Error: "AZURE_USE_AUTHENTICATION and USE_AUTH0_AUTHENTICATION cannot both be true"
   - Solution: Set only one authentication method to `true`

2. **Chat History Without Authentication**
   - Error: "USE_CHAT_HISTORY_COSMOS requires either authentication method"
   - Solution: Enable either `AZURE_USE_AUTHENTICATION` or `USE_AUTH0_AUTHENTICATION`

3. **Missing User ID**
   - Error: "User ID not found"
   - Solution: Ensure Auth0 is properly configured to pass user identity in headers

### Validation Commands

```bash
# Check environment configuration
azd env get-values | grep -E "(USE_AUTH0_AUTHENTICATION|AZURE_USE_AUTHENTICATION|USE_CHAT_HISTORY_COSMOS)"

# Verify deployment status
azd show
```
