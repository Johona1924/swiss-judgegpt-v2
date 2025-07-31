"""
BGer (Swiss Federal Court) published judgments processor.

Transforms markdown files like "81 II 117.md" into structured JSON documents.

Input Format:
- Markdown files (.md) with structured content
- Filename pattern: "{volume} {roman} {page}.md" (e.g., "81 II 117.md")
- Content includes case title in first # header and metadata as - **key**: value lists

Output Format:
- JSON with extracted metadata plus full content
- Filename converted to underscores: "81_II_117.json"

Example:
    Input: "81 II 117.md"
    ```
    # Beschwerde in Strafsachen gegen Urteil des Obergerichts
    
    - **Jahr**: 2023
    - **Gericht**: Bundesgericht
    
    Full judgment content...
    ```
    
    Output: "81_II_117.json"
    {
        "title": "Beschwerde in Strafsachen gegen Urteil des Obergerichts",
        "content": "# Beschwerde in Strafsachen...",
        "filename": "81_II_117.json",
        "last_updated": "2024-01-15T10:30:00+00:00",
        "year": "2023-01-01T00:00:00+00:00",
        "volume_number": 81,
        "volume_roman": "II",
        "first_page": 117
    }
"""

import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from core.types import DocumentProcessor, add_common_metadata
from schemas.published_bger import PUBLISHED_BGER_SCHEMA


class PublishedBgerProcessor(DocumentProcessor):
    """Processor for BGer judgment markdown files."""
    
    NAME = "published_bger"
    INPUT_EXTENSION = ".md"
    OUTPUT_EXTENSION = ".json"
    SCHEMA = PUBLISHED_BGER_SCHEMA
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

        output_filename = self.get_output_filename(input_filename=filename)
        
        # Transform year to ISO format if present
        if "year" in json_obj:
            json_obj["year"] = self._extract_and_format_year(json_obj["year"])
        
        return add_common_metadata(json_obj,filename=output_filename)
    
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