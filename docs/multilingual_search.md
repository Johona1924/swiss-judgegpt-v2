# Multilingual Search Support 



This document describes the multilingual search functionality that allows querying across multiple language-specific content fields in a single Azure AI Search index.

## Setup Requirements

### Index Schema Requirements

For multilingual search to work, your Azure AI Search index must have:

1. **Language-specific content fields** named with the pattern `content_{language_code}`:
   - `content_de` for German content
   - `content_it` for Italian content  
   - `content_fr` for French content

2. **A language field** for filtering, named `language`, containing the language abbreviation according to ISO 639-1 (e.g. 'en', 'de', 'it', or 'fr').

### Example Index Schema

```json
{
  "fields": [
    {
      "name": "id",
      "type": "Edm.String",
      "key": true,
      "searchable": false,
      "filterable": true,
      "retrievable": true
    },
    {
      "name": "content_de",
      "type": "Edm.String",
      "searchable": true,
      "filterable": false,
      "retrievable": true
    },
    {
      "name": "content_it",
      "type": "Edm.String", 
      "searchable": true,
      "filterable": false,
      "retrievable": true
    },
    {
      "name": "content_fr",
      "type": "Edm.String",
      "searchable": true,
      "filterable": false,
      "retrievable": true
    },
    {
      "name": "language",
      "type": "Edm.String",
      "searchable": false,
      "filterable": true,
      "retrievable": true
    }
  ]
}
```

### Environment Configuration

Enable multilingual search by setting the environment variable:

```bash
ENABLE_MULTILINGUAL_SEARCH=true
```

## How It Works

### 1. Index Validation
On startup, the system:
- Connects to the Azure AI Search index
- Validates the schema for multilingual support
- Identifies available language-specific content fields
- Logs whether multilingual search is supported

### 2. Query Processing
When multilingual search is enabled:
- The LLM generates language-specific search queries using function calling
- Each query targets a specific language (DE, IT, FR)
- The system extracts individual queries from the LLM response

### 3. Parallel Search Execution
For each language:
- Searches only the language-specific content field (e.g., `content_de`)
- Applies a language filter (`language eq 'de'`)
- Retrieves top K results per language
- Executes all language searches in parallel for efficiency

### 4. Result Reranking
After collecting results from all languages:
- Combines all documents into a single collection
- Sorts by reranker score (if available), then by search score
- Returns the top K documents overall

### 5. Fallback Behavior
If multilingual search is not available:
- Falls back to traditional concatenated query approach
- Uses the existing `content` field
- Maintains backward compatibility

## Configuration Options

### Environment Variables

- `ENABLE_MULTILINGUAL_SEARCH`: Enable/disable multilingual search (default: false)

## Monitoring and Debugging

### Log Messages

The system provides detailed logging:
- Index schema validation results
- Multilingual support detection
- Language-specific search execution
- Fallback scenarios

### Error Handling

- Graceful degradation when schema doesn't support multilingual
- Individual language search failures don't break the entire operation
- Comprehensive error logging for troubleshooting

## Migration Guide

### From Single Language to Multilingual

1. **Update your index schema** to include language-specific content fields
2. **Reindex your documents** with content in the appropriate language fields
3. **Set the language field** appropriately for each document
4. **Enable the feature** with `ENABLE_MULTILINGUAL_SEARCH=true`
5. **Test** that searches work across all languages

### Backward Compatibility

The system is fully backward compatible:
- Existing indexes without multilingual support continue to work
- No changes required to existing prompts or tools
- Single-language search behavior is preserved when multilingual is disabled


