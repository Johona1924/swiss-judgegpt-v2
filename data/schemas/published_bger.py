"""
JSON Schema for Published BGer Judgment documents.

This schema defines the structure for Swiss Federal Court (BGer) published judgments
transformed from markdown to JSON format.
"""

PUBLISHED_BGER_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "https://judgegpt.ch/schemas/published-bger-v1.json",
    "title": "Published BGer Judgment",
    "description": "Schema for Swiss Federal Court published judgment documents",
    "type": "object",
    "required": ["title", "content", "filename", "last_updated"],
    "properties": {
        "title": {
            "type": "string",
            "description": "Case title extracted from first markdown header",
            "examples": ["Beschwerde in Strafsachen", "Verwaltungsgerichtsbeschwerde"]
        },
        "content": {
            "type": "string", 
            "description": "Full markdown content of the judgment"
        },
        "filename": {
            "type": "string",
            "description": "Output filename with underscores (spaces removed)",
            "pattern": "^\\d+_[IVX]+[AB]?_\\d+\\.json$",
            "examples": ["81_II_117.json", "149_I_123.json"]
        },
        "last_updated": {
            "type": "string",
            "format": "date-time", 
            "description": "ISO 8601 timestamp when JSON was generated"
        },
        "year": {
            "type": ["string", "null"],
            "format": "date-time",
            "description": "Judgment year in ISO 8601 format, extracted from metadata"
        },
        "volume_number": {
            "type": ["integer", "null"],
            "description": "BGE volume number extracted from filename",
            "examples": [81, 149, 116]
        },
        "volume_roman": {
            "type": ["string", "null"], 
            "description": "BGE volume roman numeral (I, II, III, IV, V, IA, IB, etc.)",
            "enum": ["I", "II", "III", "IV", "V", "IA", "IB"],
            "examples": ["I", "II", "III", "IA", "IB"]
        },
        "first_page": {
            "type": ["integer", "null"],
            "description": "First page number of judgment in BGE volume",
            "examples": [117, 428, 1]
        }
    },
    "additionalProperties": True,
    "examples": [
        {
            "title": "Beschwerde in Strafsachen",
            "content": "# Beschwerde in Strafsachen\n\n- **Jahr**: 2023\n- **Gericht**: Bundesgericht\n\nFull content...",
            "filename": "81_II_117.json",
            "last_updated": "2024-01-15T10:30:00+00:00", 
            "year": "2023-01-01T00:00:00+00:00",
            "volume_number": 81,
            "volume_roman": "II",
            "first_page": 117
        }
    ]
}
