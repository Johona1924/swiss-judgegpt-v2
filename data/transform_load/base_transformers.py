"""
Base classes and utilities for document transformation.

This module provides base classes and utilities that can be extended
for different document types and schemas.
"""

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pathlib import Path


class BaseDocumentTransformer(ABC):
    """
    Abstract base class for document transformers.
    
    Provides common functionality and defines the interface for
    document transformation implementations.
    """
    
    # Subclasses should define their schema
    SCHEMA: Dict[str, Any] = {}
    
    @abstractmethod
    def transform_document(self, content: str, filename: str) -> Dict[str, Any]:
        """
        Transform raw document content to JSON object.
        
        Args:
            content: Raw document content
            filename: Original filename
            
        Returns:
            Dictionary representing the transformed document
        """
        pass
    
    @abstractmethod
    def get_output_filename(self, input_filename: str) -> str:
        """
        Get the output filename for the transformed document.
        
        Args:
            input_filename: Original input filename
            
        Returns:
            Output filename for the transformed document
        """
        pass
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this transformer."""
        return self.SCHEMA.copy()
    
    def validate_document(self, document: Dict[str, Any]) -> bool:
        """
        Validate document against schema (basic validation).
        
        Args:
            document: Document to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            schema = self.get_schema()
            required_fields = schema.get("properties", {}).get("required", [])
            
            # Check required fields
            for field in required_fields:
                if field not in document:
                    print(f"Missing required field: {field}")
                    return False
            
            return True
        except Exception as e:
            print(f"Validation error: {e}")
            return False
    
    def add_common_metadata(self, document: Dict[str, Any], filename: str) -> Dict[str, Any]:
        """
        Add common metadata to document.
        
        Args:
            document: Document to enhance
            filename: Output filename
            
        Returns:
            Document with added metadata
        """
        document["filename"] = filename
        document["last_updated"] = datetime.now(timezone.utc).isoformat(
            sep="T", timespec="seconds"
        )
        return document


class SchemaRegistry:
    """
    Registry for managing different document schemas.
    """
    
    def __init__(self):
        self._schemas: Dict[str, Dict[str, Any]] = {}
        self._transformers: Dict[str, BaseDocumentTransformer] = {}
    
    def register_schema(self, name: str, schema: Dict[str, Any]) -> None:
        """Register a schema by name."""
        self._schemas[name] = schema
    
    def register_transformer(self, name: str, transformer: BaseDocumentTransformer) -> None:
        """Register a transformer by name."""
        self._transformers[name] = transformer
        # Auto-register schema if transformer has one
        if hasattr(transformer, 'SCHEMA') and transformer.SCHEMA:
            self.register_schema(name, transformer.SCHEMA)
    
    def get_schema(self, name: str) -> Optional[Dict[str, Any]]:
        """Get schema by name."""
        return self._schemas.get(name)
    
    def get_transformer(self, name: str) -> Optional[BaseDocumentTransformer]:
        """Get transformer by name."""
        return self._transformers.get(name)
    
    def list_schemas(self) -> List[str]:
        """List all registered schema names."""
        return list(self._schemas.keys())
    
    def list_transformers(self) -> List[str]:
        """List all registered transformer names."""
        return list(self._transformers.keys())
    

class ConfigurationManager:
    """
    Manager for transformer configurations.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration manager.
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = config_path
        self.config = self._load_config() if config_path else {}
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        try:
            config_file = Path(self.config_path)
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading config from {self.config_path}: {e}")
        return {}
    
    def get_transformer_config(self, transformer_name: str) -> Dict[str, Any]:
        """Get configuration for a specific transformer."""
        return self.config.get("transformers", {}).get(transformer_name, {})
    
    def get_schema_config(self, schema_name: str) -> Dict[str, Any]:
        """Get configuration for a specific schema."""
        return self.config.get("schemas", {}).get(schema_name, {})
    
    def save_config(self) -> None:
        """Save current configuration to file."""
        if not self.config_path:
            raise ValueError("No config path specified")
        
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config to {self.config_path}: {e}")


# Global registry instance
default_registry = SchemaRegistry()


def get_default_registry() -> SchemaRegistry:
    """Get the default global schema registry."""
    return default_registry
