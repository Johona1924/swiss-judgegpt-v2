"""
processor registry and discovery.

Simple registry for document processors without boilerplate.
To add a new processor:
1. Create processor class implementing Documentprocessor protocol
2. Add to processorS dict below
3. Done!
"""

from typing import Optional
from core.types import DocumentProcessor

# Import processors
from document_processors.published_bger import PublishedBgerProcessor
from document_processors.published_bger_trilingual import PublishedBgerTrilingualProcessor
from document_processors.faulty_processor import FaultyProcessor

# processor registry - add new processors here
PROCESSORS = {
    "published_bger": PublishedBgerProcessor,
    "published_bger_trilingual": PublishedBgerTrilingualProcessor,
    "faulty_test_processor" : FaultyProcessor
}

def get_processor(name: str) -> Optional[DocumentProcessor]:
    """Get processor instance by name."""
    processor_class = PROCESSORS.get(name)
    return processor_class() if processor_class else None


def list_processor() -> list[str]:
    """List available processor names."""
    return list(PROCESSORS.keys())


def get_processor_info(name: str) -> dict:
    """Get information about a processor."""
    processor_class = PROCESSORS.get(name)
    if not processor_class:
        return {}
    
    return {
        "name": getattr(processor_class, "NAME", name),
        "input_extension": getattr(processor_class, "INPUT_EXTENSION", ""),
        "output_extension": getattr(processor_class, "OUTPUT_EXTENSION", ""),
        "description": processor_class.__doc__ or "",
        "has_schema": hasattr(processor_class, "SCHEMA")
    }
