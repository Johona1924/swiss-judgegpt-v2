import logging
import os
from typing import Any, Optional

from .authentication_auth0 import get_authenticated_user_details


class Auth0AuthenticationHelper:
    """Authentication helper for Auth0 integration"""
    
    def __init__(self, use_auth0_authentication: bool = False):
        self.use_auth0_authentication = use_auth0_authentication
        
    async def get_auth_claims_if_enabled(self, request_headers):
        """Get auth claims from Auth0 if enabled, otherwise return empty dict"""
        if not self.use_auth0_authentication:
            return {}
            
        try:
            user_details = get_authenticated_user_details(request_headers)
            # Convert Auth0 user details to the format expected by the rest of the app
            auth_claims = {
                "oid": user_details.get("user_principal_id"),  # Use Auth0 user ID as the OID
                "name": user_details.get("user_name"),
                "preferred_username": user_details.get("user_name"),
                "auth_provider": user_details.get("auth_provider", "auth0"),
            }
            
            # Ensure we have a user ID
            if not auth_claims.get("oid"):
                logging.warning("No user_principal_id found in Auth0 headers")
                auth_claims["oid"] = "unknown_user"
                
            return auth_claims
            
        except Exception as e:
            logging.exception("Error extracting Auth0 user details: %s", e)
            return {}
    
    async def check_path_auth(self, path: str, auth_claims: dict[str, Any], search_client) -> bool:
        """For Auth0, we don't implement path-based access control, always return True"""
        # Since the requirement states no user authorization or access controls needed for Auth0
        return True
    
    def get_auth_setup_for_client(self) -> dict[str, Any]:
        """Return auth setup configuration for the client"""
        return {
            "useLogin": self.use_auth0_authentication,
            "requireAccessControl": False,  # No access control for Auth0
            "enableUnauthenticatedAccess": not self.use_auth0_authentication,
            "msalConfig": None,  # No MSAL config needed for Auth0
        }
    
    def build_security_filters(self, overrides: dict[str, Any], auth_claims: dict[str, Any]):
        #Not implemented yet
        return None
