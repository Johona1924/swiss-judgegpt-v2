import argparse
import os
import sys
from typing import Optional, Dict, Any

import yaml
from dotenv import load_dotenv


class ConfigLoader:
    """Handles loading configuration from profiles and environment variables."""
    
    def __init__(self, config_file: str = "configs.yaml", env_file: str = ".env"):
        self.config_file = config_file
        self.env_file = env_file
        self.configs = {}
        self._load_environment()
        self._load_configs()
    
    def _load_environment(self):
        """Load environment variables from .env file if it exists."""
        if os.path.exists(self.env_file):
            load_dotenv(self.env_file)
    
    def _load_configs(self):
        """Load configuration profiles from YAML file."""
        if not os.path.exists(self.config_file):
            return
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.configs = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"⚠️  Warning: Could not load config file {self.config_file}: {e}")
            self.configs = {}

    def resolve_connection_string(self, config: Dict[str, Any]) -> str:
        """Resolve connection string from environment."""
        # Check if connection string is in config
        if "connection_string_name" in config:
            connection_string_name = config["connection_string_name"]
            
            # Otherwise, treat it as an environment variable name
            env_conn_str = os.getenv(connection_string_name)
            if env_conn_str:
                return env_conn_str
            else:
                raise ValueError(
                    f"❌ Environment variable '{connection_string_name}' not found.\n"
                    f"   Make sure '{connection_string_name}' is defined in your .env file"
                )
        
        raise ValueError(
            "❌ No Azure Storage connection string found.\n"
            "   Please either:\n"
            "   • Add connection_string_name to your profile in configs.yaml, referencing a valid env variable like 'CONNECTION_STRING_TEST') OR\n"
            "   • Use --connection-string argument"
        )
    
    def list_profiles(self) -> list[str]:
        """List available configuration profiles."""
        return list(self.configs.keys())
    
    def get_profile_config(self, profile_name: str) -> Dict[str, Any]:
        """Get configuration for a specific profile."""
        if profile_name not in self.configs:
            available_profiles = list(self.configs.keys())
            if available_profiles:
                raise ValueError(
                    f"❌ Profile '{profile_name}' not found.\n"
                    f"Available profiles: {', '.join(available_profiles)}"
                )
            else:
                raise ValueError(
                    f"❌ Profile '{profile_name}' not found and no config file available.\n"
                    f"Expected config file: {self.config_file}"
                )
        profile_config = self.configs[profile_name].copy()

        # Resolve connection string by retrieving corresponding env variable
        profile_config.update({"connection_string" : self.resolve_connection_string(profile_config)})

        return profile_config

def merge_config_with_args(config: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    """Merge profile config with command line arguments. CLI args take precedence."""
    result = {}
    
    # Start with profile config
    result.update(config)
    
    # Override with CLI args (only if they're not None/default)
    if args.processor:
        result["processor"] = args.processor
    if args.connection_string:
        result["connection_string"] = args.connection_string
    if args.container:
        result["container"] = args.container
    if args.folder:
        result["folder"] = args.folder
    if args.range:
        result["range"] = args.range
    if args.batch_size != 10:  # 10 is the default
        result["batch_size"] = args.batch_size
    if args.max_workers != 5:  # 5 is the default
        result["max_workers"] = args.max_workers
    if args.max_retries != 3:  # 3 is the default
        result["max_retries"] = args.max_retries
    if args.individual_uploads:
        result["individual_uploads"] = args.individual_uploads
    if args.skip_validation:
        result["skip_validation"] = args.skip_validation
    
    return result
