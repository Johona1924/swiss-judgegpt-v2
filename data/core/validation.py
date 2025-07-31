"""
JSON Schema validation utilities.

This module provides utilities for validating documents against JSON schemas
before uploading to blob storage.
"""

# IMPORTANT : even though setting a "format" in the schema, the format is currently not validated 
# by default by the jsonschema validation
# TODO : implement format validation
# https://python-jsonschema.readthedocs.io/en/latest/validate/#validating-formats

import json
from typing import Dict, Any, List, Optional
from .types import DocumentProcessor
from jsonschema import Draft7Validator
import logging

logger = logging.getLogger(__name__)


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

    print(f"name : {__name__}")
    
    try:
        # Use Draft7Validator for better error messages
        validator = Draft7Validator(schema)
        errors = list(validator.iter_errors(document))

        logger.debug(f"errors : {errors}")
        
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
    
def validate_processor_schema(processor: DocumentProcessor) -> None:
        """
        Validate that processor has a valid JSON schema when validation is required.
        
        Args:
            processor: processor that should have a schema
            
        Raises:
            ValueError: If no schema is available or schema is invalid when validation is required
        """
        processor_name = getattr(processor, 'NAME', processor.__class__.__name__)
        
        # Check if processor has SCHEMA attribute
        if not hasattr(processor, 'SCHEMA') or not processor.SCHEMA:
            raise ValueError(
                f"❌ Schema validation is enabled but processor '{processor_name}' "
                f"has no SCHEMA attribute or it's empty.\n"
                f"   To fix this:\n"
                f"   • Add a SCHEMA attribute to the processor class, OR\n"
                f"   • Use --skip-validation to disable schema validation"
            )
        
        # Validate that the schema itself is a valid JSON schema
        try:
            Draft7Validator.check_schema(processor.SCHEMA)
        except Exception as e:
            raise ValueError(
                f"❌ Schema validation is enabled but processor '{processor_name}' "
                f"has an invalid JSON schema.\n"
                f"   Schema error: {str(e)}\n"
                f"   To fix this:\n"
                f"   • Fix the SCHEMA attribute in the processor class, OR\n"
                f"   • Use --skip-validation to disable schema validation"
            )
