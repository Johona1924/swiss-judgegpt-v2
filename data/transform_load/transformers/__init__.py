"""
Transformer registry and discovery.

Simple registry for document transformers without boilerplate.
To add a new transformer:
1. Create transformer class implementing DocumentTransformer protocol
2. Add to TRANSFORMERS dict below
3. Done!
"""

from typing import Optional
from core.types import DocumentTransformer

# Import transformers
from transformers.published_bger import PublishedBgerTransformer
from transformers.published_bger_trilingual import PublishedBgerTrilingualTransformer

# Transformer registry - add new transformers here
TRANSFORMERS = {
    "published_bger": PublishedBgerTransformer,
    "published_bger_trilingual": PublishedBgerTrilingualTransformer,
}


def get_transformer(name: str) -> Optional[DocumentTransformer]:
    """Get transformer instance by name."""
    transformer_class = TRANSFORMERS.get(name)
    return transformer_class() if transformer_class else None


def list_transformers() -> list[str]:
    """List available transformer names."""
    return list(TRANSFORMERS.keys())


def get_transformer_info(name: str) -> dict:
    """Get information about a transformer."""
    transformer_class = TRANSFORMERS.get(name)
    if not transformer_class:
        return {}
    
    return {
        "name": getattr(transformer_class, "NAME", name),
        "input_extension": getattr(transformer_class, "INPUT_EXTENSION", ""),
        "output_extension": getattr(transformer_class, "OUTPUT_EXTENSION", ""),
        "description": transformer_class.__doc__ or "",
        "has_schema": hasattr(transformer_class, "SCHEMA")
    }
