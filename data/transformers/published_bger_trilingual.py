"""
BGer trilingual transformer for Switzerland's three official languages.

Same as PublishedBgerTransformer but creates language-specific content fields
for German (de), French (fr), and Italian (it).

Output Format:
- Includes content_de, content_fr, content_it fields
- Only the detected language field contains content, others are empty strings

Example:
    Input: "81 II 117.md" (German content)
    
    Output: "81_II_117.json"
    {
        "title": "Beschwerde in Strafsachen",
        "content_de": "# Beschwerde in Strafsachen...",  # Full content if German
        "content_fr": "",                                   # Empty if not French
        "content_it": "",                                   # Empty if not Italian
        "language": "de",
        "filename": "81_II_117.json",
        "last_updated": "2024-01-15T10:30:00+00:00",
        ...
    }
"""

import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from core.types import DocumentTransformer, add_common_metadata
from schemas.published_bger_trilingual import PUBLISHED_BGER_TRILINGUAL_SCHEMA


class PublishedBgerTrilingualTransformer:
    """Trilingual BGer transformer with language-specific content fields."""
    
    NAME = "published_bger_trilingual"
    INPUT_EXTENSION = ".md"
    OUTPUT_EXTENSION = ".json"
    SCHEMA = PUBLISHED_BGER_TRILINGUAL_SCHEMA
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
