"""
JSON Schema for Trilingual Published BGer Judgment documents.

This schema defines the structure for Swiss Federal Court (BGer) published judgments
with language-specific content fields for German (de), French (fr), and Italian (it).
"""

PUBLISHED_BGER_TRILINGUAL_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "https://judgegpt.ch/schemas/published-bger-trilingual-v1.json",
    "title": "Published BGer Judgment (Trilingual)",
    "description": "Schema for Swiss Federal Court published judgment documents with language-specific content fields",
    "type": "object",
    "required": ["title", "content_de", "content_fr", "content_it", "language", "filename", "last_updated"],
    "properties": {
        "title": {
            "type": "string",
            "description": "Case title extracted from first markdown header",
            "examples": ["Beschwerde in Strafsachen", "Recours en matière pénale", "Ricorso in materia penale"]
        },
        "content_de": {
            "type": "string", 
            "description": "Full markdown content if detected language is German, empty string otherwise"
        },
        "content_fr": {
            "type": "string", 
            "description": "Full markdown content if detected language is French, empty string otherwise"
        },
        "content_it": {
            "type": "string", 
            "description": "Full markdown content if detected language is Italian, empty string otherwise"
        },
        "language": {
            "type": "string",
            "enum": ["de", "fr", "it"],
            "description": "Detected language of the judgment content"
        },
        "filename": {
            "type": "string",
            "description": "Output filename with underscores (spaces removed)",
            "pattern": "^[0-9]+_[IVX]+[AB]?_[0-9]+\\.json$",
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
            "content_de": "# Beschwerde in Strafsachen\n\n- **Jahr**: 2023\n- **Gericht**: Bundesgericht\n\nFull content...",
            "content_fr": "",
            "content_it": "",
            "language": "de",
            "filename": "81_II_117.json",
            "last_updated": "2024-01-15T10:30:00+00:00", 
            "year": "2023-01-01T00:00:00+00:00",
            "volume_number": 81,
            "volume_roman": "II",
            "first_page": 117
        },
        {
            "title": "Recours en matière pénale",
            "content_de": "",
            "content_fr": "# Recours en matière pénale\n\n- **Année**: 2023\n- **Tribunal**: Tribunal fédéral\n\nContenu complet...",
            "content_it": "",
            "language": "fr",
            "filename": "82_I_45.json",
            "last_updated": "2024-01-15T10:30:00+00:00", 
            "year": "2023-01-01T00:00:00+00:00",
            "volume_number": 82,
            "volume_roman": "I",
            "first_page": 45
        }
    ]
}
