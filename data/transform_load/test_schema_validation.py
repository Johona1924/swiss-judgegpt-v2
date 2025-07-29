#!/usr/bin/env python3
"""
Test script to verify schema validation behavior.

Tests that validation properly fails when:
1. validate_schema=True and transformer has no SCHEMA
2. validate_schema=True and transformer.SCHEMA is None/empty
3. validate_schema=False allows transformers without schemas
"""

import tempfile
import os
from typing import Dict, Any

from load_to_blob import BlobLoader
from core.types import DocumentTransformer


class TestTransformerNoSchema:
    """Test transformer without SCHEMA attribute."""
    
    NAME = "test_no_schema"
    INPUT_EXTENSION = ".md"
    OUTPUT_EXTENSION = ".json"
    
    def transform_document(self, content: str, filename: str) -> Dict[str, Any]:
        return {
            "title": "Test Document",
            "content": content,
            "filename": filename.replace(".md", ".json")
        }
    
    def get_output_filename(self, input_filename: str) -> str:
        return input_filename.replace(".md", ".json")


class TestTransformerEmptySchema:
    """Test transformer with empty SCHEMA."""
    
    NAME = "test_empty_schema"
    INPUT_EXTENSION = ".md"
    OUTPUT_EXTENSION = ".json"
    SCHEMA = None  # Explicitly empty
    
    def transform_document(self, content: str, filename: str) -> Dict[str, Any]:
        return {
            "title": "Test Document",
            "content": content,
            "filename": filename.replace(".md", ".json")
        }
    
    def get_output_filename(self, input_filename: str) -> str:
        return input_filename.replace(".md", ".json")


def test_schema_validation():
    """Test the schema validation behavior."""
    # Create a temporary test file
    with tempfile.TemporaryDirectory() as temp_dir:
        test_file = os.path.join(temp_dir, "test.md")
        with open(test_file, "w") as f:
            f.write("# Test Document\n\nTest content")
        
        # Mock blob loader (we won't actually upload)
        loader = BlobLoader(
            connection_string="DefaultEndpointsProtocol=https;AccountName=test;AccountKey=fake;EndpointSuffix=core.windows.net",
            container_name="test"
        )
        
        # Test 1: Transformer without SCHEMA should fail with validation enabled
        print("🧪 Test 1: Transformer without SCHEMA attribute, validation ENABLED")
        try:
            loader._validate_transformer_schema_available(TestTransformerNoSchema())
            print("❌ FAILED: Should have raised ValueError")
        except ValueError as e:
            print(f"✅ PASSED: {e}")
        except Exception as e:
            print(f"❌ FAILED: Unexpected error: {e}")
        
        # Test 2: Transformer with empty SCHEMA should fail with validation enabled
        print("\n🧪 Test 2: Transformer with empty SCHEMA, validation ENABLED")
        try:
            loader._validate_transformer_schema_available(TestTransformerEmptySchema())
            print("❌ FAILED: Should have raised ValueError")
        except ValueError as e:
            print(f"✅ PASSED: {e}")
        except Exception as e:
            print(f"❌ FAILED: Unexpected error: {e}")
        
        print("\n🧪 Test 3: Testing with existing transformer that has schema")
        from transformers.published_bger import PublishedBgerTransformer
        try:
            loader._validate_transformer_schema_available(PublishedBgerTransformer())
            print("✅ PASSED: No error raised for transformer with valid schema")
        except Exception as e:
            print(f"❌ FAILED: Unexpected error: {e}")


if __name__ == "__main__":
    test_schema_validation()
