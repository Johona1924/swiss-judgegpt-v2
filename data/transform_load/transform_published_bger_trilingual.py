"""
BGer (Bundesgericht) published judgments transformer.

This module implements document transformation for published BGer judgments
from markdown format to a structured JSON schema.
"""

import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from base_transformers import BaseDocumentTransformer, get_default_registry


class PublishedBgerTransformerTrilingual(BaseDocumentTransformer):
    """
    Transformer for published BGer judgment markdown files.
    
    Transforms markdown files with names like "81 II 117.md", "116 II 428.md"
    into structured JSON documents following the BGer schema.
    """
    
    # JSON Schema for validation reference
    SCHEMA = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "The title of the case, extracted from the first markdown header."
            },
            "last_updated": {
                "type": "string",
                "format": "ISO 8601",
                "description": "The timestamp of when the JSON object was last updated, with UTC timezone."
            },
            "content_de": {
                "type": "string",
                "description": "The full content of the markdown file if detected_language is GERMAN, empty string otherwise."
            },
            "content_fr": {
                "type": "string",
                "description": "The full content of the markdown file if the detected_language is FRENCH, empty string otherwise."
            },
            "content_it": {
                "type": "string",
                "description": "The full content of the markdown file if the detected_language is ITALIAN, empty string otherwise."
            },
            "filename": {
                "type": "string",
                "description": "The name of the file, converted to JSON format, with underscores instead of whitespaces."
            },
            "year": {
                "type": ["string", "null"],
                "format": "ISO 8601",
                "description": "Year of the judgment, as extracted from the **year** list entry, with additional Regex."
            },
            "volume_number": {
                "type": ["integer", "null"],
                "description": "Bandzahl (volume number), without year. Example: 146 for BGE 146 III 63, E. 4.2."
            },
            "first_page": {
                "type": ["integer", "null"],
                "description": "First page number. Example: 63 for BGE 146 III 63, E. 4.2."
            },
            "volume_roman": {
                "type": ["string", "null"],
                "enum": ["I", "II", "III", "IV", "V", "IA", "IB"],
                "description": "Teilband, e.g. III in BGE 146 III 63, E. 4.2."
            },
            "unpublished_case": {
                "type": "string",
                "description": "Unpublished case indicator"
            },
            "language": {
                "type": "string",
                "description": "Language of the judgment"
            }
        },
        "required": ["title", "last_updated", "content_de", "content_fr", "content_it", "filename"],
        "additionalProperties": True
    }
    
    VALID_ROMAN_NUMERALS = ["I", "II", "III", "IV", "V", "IA", "IB"]
    
    def transform_document(self, content: str, filename: str) -> Dict[str, Any]:
        """
        Transform a BGer markdown document to JSON.
        
        Args:
            content: Raw markdown content
            filename: Original filename
            
        Returns:
            Dictionary representing the transformed document
        """
        # Parse basic content structure
        json_obj = self._parse_markdown_content(content)
        
        # Extract filename-based metadata
        json_obj.update(self._extract_filename_metadata(filename))

        json_obj = self._process_language_and_content(json_obj)
        
        # Transform year to ISO format if present
        if "year" in json_obj:
            json_obj["year"] = self._extract_and_format_year(json_obj["year"])
        
        return json_obj
    
    
    def get_output_filename(self, input_filename: str) -> str:
        """Convert input filename to JSON output filename."""
        return input_filename.replace(" ", "_").replace(".md", ".json")
    
    def _parse_markdown_content(self, content: str) -> Dict[str, Any]:
        """Parse markdown content into base JSON structure."""
        lines = content.strip().splitlines()
        result = {
            "title": "",
            "content": content.strip(),
        }
        
        # Extract title from first markdown header
        if lines and lines[0].strip().startswith("# "):
            result["title"] = lines[0].lstrip("#").strip()
        
        # Parse metadata from list items (- **key**: value)
        metadata_pattern = re.compile(r"- \*\*(.+?)\*\*: ?(.*)")
        for line in lines:
            match = metadata_pattern.match(line)
            if match:
                key, value = match.groups()
                result[key.strip()] = value.strip() if value else None
        
        return result
    
    def _process_language_and_content(self, json_obj: dict) -> dict:
        """
        Extracts language from 'detected_language' field, assignes to single language field, and assignes conent to now content_LANG field
        """
        # Get language (prefer detected_language over language)
        language = json_obj.pop("detected_language")
        
        # Fast validation - only check what's absolutely necessary
        if language not in {"de", "fr", "it"}:
            raise ValueError(f"Invalid language: {language}")
        
        json_obj["language"] = language
        
        # Assign content efficiently
        content = json_obj.pop("content", "")
        json_obj.update({
            "content_de": content if language == "de" else "",
            "content_fr": content if language == "fr" else "",
            "content_it": content if language == "it" else ""
        })
    
        return json_obj
    
    def _extract_filename_metadata(self, filename: str) -> Dict[str, Any]:
        """Extract metadata from BGer filename format."""
        return {
            "volume_number": self._extract_volume_number(filename),
            "volume_roman": self._extract_volume_roman(filename),
            "first_page": self._extract_first_page(filename)
        }
    
    def _extract_volume_number(self, filename: str) -> Optional[int]:
        """
        Extract volume number from filename.
        
        Args:
            filename: Filename like '116 IA 316.md' or '89 II 214.md'
            
        Returns:
            Volume number as integer or None
        """
        try:
            parts = filename.split(" ")
            if parts and parts[0].isdigit():
                return int(parts[0])
            else:
                print(f"Could not extract volume number from file: {filename}")
                return None
        except Exception as e:
            print(f"Error extracting volume number from '{filename}': {e}")
            return None
    
    def _extract_volume_roman(self, filename: str) -> Optional[str]:
        """
        Extract Roman numeral volume from filename.
        
        Args:
            filename: Filename like '116 IA 316.md'
            
        Returns:
            Roman numeral volume or None
        """
        try:
            parts = filename.split(" ")
            if len(parts) > 1:
                volume_roman = parts[1].strip().upper()
                if volume_roman in self.VALID_ROMAN_NUMERALS:
                    return volume_roman
                else:
                    print(f"Invalid Roman numeral volume '{volume_roman}' in file: {filename}")
                    return None
            else:
                print(f"Could not extract Roman volume from file: {filename}")
                return None
        except Exception as e:
            print(f"Error extracting Roman volume from '{filename}': {e}")
            return None
    
    def _extract_first_page(self, filename: str) -> Optional[int]:
        """
        Extract first page number from filename.
        
        Args:
            filename: Filename like '116 IA 316.md'
            
        Returns:
            First page number as integer or None
        """
        try:
            parts = filename.split(" ")
            if len(parts) > 2:
                first_page_str = parts[2].replace(".md", "")
                if first_page_str.isdigit():
                    return int(first_page_str)
                else:
                    print(f"Invalid first page number '{first_page_str}' in file: {filename}")
                    return None
            else:
                print(f"Could not extract first page from file: {filename}")
                return None
        except Exception as e:
            print(f"Error extracting first page from '{filename}': {e}")
            return None
    
    def _extract_and_format_year(self, input_str: str) -> Optional[str]:
        """
        Extract year from string and convert to ISO 8601 format.
        
        Args:
            input_str: String potentially containing a year
            
        Returns:
            Year in ISO 8601 format or None
        """
        if not input_str:
            return None
        
        try:
            year_pattern = r"(19\d{2}|20\d{2})"
            match = re.search(year_pattern, input_str)
            if match:
                year_int = int(match.group(0))
                return datetime(year_int, 1, 1, tzinfo=timezone.utc).isoformat()
            else:
                print(f"Could not extract year from input string: {input_str}")
                return None
        except Exception as e:
            print(f"Error processing year from '{input_str}': {e}")
            return None


def main():
    """Main function for interactive execution."""
    from load_to_blob import InteractiveBlobLoader
    
    print("BGer Published Judgments Transformer")
    print("=" * 40)
    
    # Create transformer and register it
    transformer = PublishedBgerTransformerTrilingual()
    registry = get_default_registry()
    registry.register_transformer("published_bger_trilingual", transformer)
    
    # Create loader and run interactive processing
    loader = InteractiveBlobLoader.from_user_input()
    loader.interactive_process_files(transformer, file_extension=".md")


if __name__ == "__main__":
    main()
