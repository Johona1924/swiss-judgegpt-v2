"""
JSON Schema validation utilities.

This module provides utilities for validating documents against JSON schemas
before uploading to blob storage.
"""

import json
from typing import Dict, Any, List, Optional
try:
    import jsonschema
    from jsonschema import validate, ValidationError, Draft7Validator
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False


class ValidationResult:
    """Result of document validation."""
    
    def __init__(self, is_valid: bool, errors: List[str] = None):
        self.is_valid = is_valid
        self.errors = errors or []
    
    def __bool__(self):
        return self.is_valid
    
    def __str__(self):
        if self.is_valid:
            return "Valid"
        return f"Invalid: {'; '.join(self.errors)}"


def validate_document(document: Dict[str, Any], schema: Dict[str, Any]) -> ValidationResult:
    """
    Validate a document against a JSON schema.
    
    Args:
        document: Document to validate
        schema: JSON schema to validate against
        
    Returns:
        ValidationResult with validation status and errors
    """
    if not JSONSCHEMA_AVAILABLE:
        print("⚠️  Warning: jsonschema not installed. Skipping validation.")
        return ValidationResult(True)
    
    try:
        # Use Draft7Validator for better error messages
        validator = Draft7Validator(schema)
        errors = list(validator.iter_errors(document))
        
        if not errors:
            return ValidationResult(True)
        
        # Format error messages
        error_messages = []
        for error in errors:
            path = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "root"
            error_messages.append(f"{path}: {error.message}")
        
        return ValidationResult(False, error_messages)
        
    except Exception as e:
        return ValidationResult(False, [f"Validation error: {str(e)}"])


def validate_required_fields(document: Dict[str, Any], required_fields: List[str]) -> ValidationResult:
    """
    Simple validation for required fields only (fallback when jsonschema not available).
    
    Args:
        document: Document to validate
        required_fields: List of required field names
        
    Returns:
        ValidationResult with validation status
    """
    missing_fields = [field for field in required_fields if field not in document]
    
    if not missing_fields:
        return ValidationResult(True)
    
    return ValidationResult(False, [f"Missing required field: {field}" for field in missing_fields])


def get_schema_required_fields(schema: Dict[str, Any]) -> List[str]:
    """Extract required fields from a JSON schema."""
    return schema.get("required", [])
