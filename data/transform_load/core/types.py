"""
Core types and utilities for document transformation.

This module provides the lean interface and common utilities without boilerplate.
"""

from typing import Protocol, Dict, Any
from datetime import datetime, timezone


class DocumentTransformer(Protocol):
    """Simple protocol for document transformers."""
    
    def transform_document(self, content: str, filename: str) -> Dict[str, Any]:
        """Transform raw document to JSON."""
        ...
    
    def get_output_filename(self, input_filename: str) -> str:
        """Get output filename for transformed document."""
        ...


def add_common_metadata(document: Dict[str, Any], filename: str) -> Dict[str, Any]:
    """Add standard metadata to document."""
    document["filename"] = filename
    document["last_updated"] = datetime.now(timezone.utc).isoformat(
        sep="T", timespec="seconds"
    )
    return document
