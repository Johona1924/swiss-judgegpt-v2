import logging
import os
from typing import Any, Optional

from . import sample_user


def get_authenticated_user_details(request_headers):
    """
    Extract user details from Azure App Service built-in authentication headers.
    
    When Azure App Service built-in authentication is enabled, it injects user identity
    information into request headers regardless of the configured identity provider
    (Auth0, Microsoft Entra ID, Google, etc.).
    """
    user_object = {}

    # Check the headers for the Principal-Id (the guid of the signed in user)
    if "X-Ms-Client-Principal-Id" not in request_headers.keys():
        # If it's not present, assume we're in development mode and return a default user
        raw_user_object = sample_user.sample_user
    else:
        # If it is present, get the user details from the App Service authentication headers
        raw_user_object = {k: v for k, v in request_headers.items()}

    user_object['user_principal_id'] = raw_user_object.get('X-Ms-Client-Principal-Id')
    user_object['user_name'] = raw_user_object.get('X-Ms-Client-Principal-Name')
    user_object['auth_provider'] = raw_user_object.get('X-Ms-Client-Principal-Idp')
    user_object['auth_token'] = raw_user_object.get('X-Ms-Token-Aad-Id-Token')
    user_object['client_principal_b64'] = raw_user_object.get('X-Ms-Client-Principal')
    user_object['aad_id_token'] = raw_user_object.get('X-Ms-Token-Aad-Id-Token')

    return user_object


class AppServiceAuthenticationHelper:
    """
    Authentication helper for Azure App Service built-in authentication.
    
    This helper works with any identity provider configured in Azure App Service
    (Auth0, Microsoft Entra ID, Google, Facebook, etc.) by extracting user information
    from the standardized headers that App Service injects into requests.
    """
    
    def __init__(self, use_appservice_authentication: bool = False):
        self.use_appservice_authentication = use_appservice_authentication
        
    async def get_auth_claims_if_enabled(self, request_headers):
        """Get auth claims from App Service authentication if enabled, otherwise return empty dict"""
        if not self.use_appservice_authentication:
            return {}
            
        try:
            user_details = get_authenticated_user_details(request_headers)
            # Convert user details to the format expected by the rest of the app
            auth_claims = {
                "oid": user_details.get("user_principal_id"),  # Use user principal ID as the OID
                "name": user_details.get("user_name"),
                "preferred_username": user_details.get("user_name"),
                "auth_provider": user_details.get("auth_provider", "unknown"),
            }
            
            # Ensure we have a user ID
            if not auth_claims.get("oid"):
                logging.warning("No user_principal_id found in App Service authentication headers")
                auth_claims["oid"] = "unknown_user"
                
            return auth_claims
            
        except Exception as e:
            logging.exception("Error extracting App Service authentication user details: %s", e)
            return {}
    
    async def check_path_auth(self, path: str, auth_claims: dict[str, Any], search_client) -> bool:
        """
        For App Service authentication, we don't implement path-based access control.
        Always return True to allow access to all documents.
        """
        return True
    
    def get_auth_setup_for_client(self) -> dict[str, Any]:
        """Return auth setup configuration for the client"""
        return {
            "useLogin": self.use_appservice_authentication,
            "requireAccessControl": False,  # No access control for App Service authentication
            "enableUnauthenticatedAccess": not self.use_appservice_authentication,
            "msalConfig": None,  # No MSAL config needed for App Service authentication
        }
    
    def build_security_filters(self, overrides: dict[str, Any], auth_claims: dict[str, Any]):
        """
        Build security filters for search queries.
        Currently not implemented for App Service authentication.
        """
        return None
