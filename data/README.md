# Document Transformation Pipeline

A lean, streamlined system for transforming documents and uploading them to Azure Blob Storage.
All parameters must be provided via command line arguments - no interactive mode.

## Project Structure

```
transform_load/
├── main.py                     # CLI interface and orchestration
├── load_to_blob.py            # Azure Blob Storage upload logic
├── requirements.txt           # Dependencies
├── README.md                  # This file
├── core/
│   └── types.py              # Protocol definitions and utilities
├── document_processors/
│   ├── __init__.py           # Processor registry
│   ├── published_bger.py     # BGer judgment processor (monolingual)
│   └── published_bger_trilingual.py  # BGer processor (trilingual)
└── schemas/
    ├── published_bger.py     # JSON schema for BGer judgments
    └── published_bger_trilingual.py  # JSON schema for trilingual BGer
```

## Usage

All arguments are required and must be provided via command line.
**Note**: The system will always ask for confirmation before uploading files, showing you exactly what will be processed and where it will be uploaded.

```bash
# Basic usage
python main.py \
    --processor published_bger_trilingual \
    --connection-string "DefaultEndpointsProtocol=https;AccountName=..." \
    --container judgments \
    --folder ./data/md_files

# With custom batch settings and file range
python main.py \
    --processor published_bger \
    --connection-string "DefaultEndpointsProtocol=https;..." \
    --container judgments \
    --folder ./data \
    --range "0:100" \
    --batch-size 50 \
    --max-workers 10 \
    --max-retries 5

# Use individual uploads instead of batch processing
python main.py \
    --processor published_bger \
    --connection-string "..." \
    --container judgments \
    --folder ./data \
    --individual-uploads

# Skip JSON schema validation (for troubleshooting)
python main.py \
    --processor published_bger \
    --connection-string "..." \
    --container judgments \
    --folder ./data \
    --skip-validation
```

### Confirmation Step

Before any files are processed or uploaded, you'll see a summary like this:

```
📋 Upload Summary:
   📁 Source folder: ./data/md_files
   ☁️  Target container: judgments
   📄 Files to process: 127
   🔧 Upload method: Batch upload
   📝 First 5 files:
      - 81 II 117.md
      - 82 I 45.md
      - 83 III 298.md
      - 84 II 156.md
      - 85 I 289.md
      ... and 122 more files

⚠️  This will upload 127 files to Azure Blob Storage.
Do you want to proceed? (yes/no):
```

Type `yes` or `y` to proceed, anything else will cancel the operation.

## Command Line Options

### Required Arguments
- `--processor`: Name of processor to use (`published_bger` or `published_bger_trilingual`)
- `--connection-string`: Azure Storage connection string
- `--container`: Blob container name
- `--folder`: Local folder containing files to process

### Optional Arguments
- `--range`: File range specification (e.g., `100:200`, `:100`, `100:`)
- `--batch-size`: Number of files per batch (default: 10)
- `--max-workers`: Concurrent upload threads (default: 5)
- `--max-retries`: Retry attempts for failed uploads (default: 3)
- `--individual-uploads`: Use individual uploads instead of batch processing
- `--skip-validation`: Skip JSON schema validation before upload (for troubleshooting)

## JSON Schema Validation

By default, all transformed documents are validated against their JSON schema before upload:

- **Automatic validation**: Documents are checked against the processor's schema
- **Detailed error reporting**: Shows exactly which fields failed validation
- **Upload prevention**: Invalid documents are not uploaded to prevent data corruption
- **Fallback validation**: Basic validation even if schema is missing
- **Optional skip**: Use `--skip-validation` to bypass validation for troubleshooting

### Validation Process

1. **Transform document**: Apply processor to input file
2. **Schema validation**: Check against JSON schema (if available)
3. **Report issues**: Show validation errors with field details
4. **Upload decision**: Only valid documents proceed to upload

Example validation error:
```
❌ Validation failed for file: example.md
   Schema: published_bger_schema
   Error: 'title' is a required property
   Error: Additional property 'invalid_field' is not allowed
```

## Available Processors

- **`published_bger`**: Swiss Federal Court (BGer) judgments (monolingual)
- **`published_bger_trilingual`**: BGer judgments with language-specific content fields

## Adding a New Processor

1. **Create processor class** in `processors/my_processor.py`:

```python
from core.types import DocumentProcessor, add_common_metadata

class MyProcessor(DocumentProcessor):
    NAME = "my_processor"
    INPUT_EXTENSION = "file-extesion" # e.g. json
    OUTPUT_EXTENSION = ".json" # has to be .json
    
    def transform_document(self, content: str, filename: str) -> dict:
        document = {
            "title": content.split('\n')[0],  # First line as title
            "content": content,
            "custom_field": "my_value"
        }
        output_filename = self.get_output_filename(filename)
        return add_common_metadata(document, output_filename)
    
    def get_output_filename(self, input_filename: str) -> str:
        return input_filename.replace(self.INPUT_EXTENSION, self.OUTPUT_EXTENSION)
```

2. **Add schema** in `schemas/my_processor.py`:

```python
MY_PROCESSOR_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "My Document Schema",
    "type": "object",
    "required": ["title", "content", "filename", "last_updated"],
    "properties": {
        "title": {"type": "string"},
        "content": {"type": "string"},
        "filename": {"type": "string"},
        "last_updated": {"type": "string", "format": "date-time"},
        "custom_field": {"type": "string"}
    }
}
```

3. **Register in `processors/__init__.py`**:

```python
from document_processors.my_processor import MyProcessor

TRANSFORMERS = {
    "published_bger": PublishedBgerProcessor,
    "published_bger_trilingual": PublishedBgerTrilingualProcessor,
    "my_processor": MyProcessor,  # Add here
}
```

4. **Done!** Your processor is now available via `--processor my_processor`.

## Input/Output Examples

### BGer Processor

**Input**: `81 II 117.md`
```markdown
# Beschwerde in Strafsachen gegen Urteil des Obergerichts

- **Jahr**: 2023
- **Gericht**: Bundesgericht

Full judgment content...
```

**Output**: `81_II_117.json`
```json
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
```

### Trilingual BGer Processor

Same input, but output includes language-specific content fields:

```json
{
  "title": "Beschwerde in Strafsachen...",
  "content_de": "# Beschwerde in Strafsachen...",  // Full content if German
  "content_fr": "",                                 // Empty if not French  
  "content_it": "",                                 // Empty if not Italian
  "language": "de",
  "filename": "81_II_117.json",
  "last_updated": "2024-01-15T10:30:00+00:00",
  ...
}
```

## Key Features

- **Streamlined CLI**: All parameters via command line - no interactive prompts
- **Mandatory confirmation**: Always asks for confirmation before uploading with detailed summary
- **JSON schema validation**: Automatic validation against processor schemas before upload
- **Organized structure**: Clear separation of concerns across folders
- **Rich schemas**: JSON Schema definitions with examples and validation
- **Convention over configuration**: Add processors by implementing protocol and registering
- **No boilerplate**: Simple protocol with just 2 required methods
- **Batch processing**: Concurrent uploads with retry logic and progress tracking
- **Range support**: Process subset of files with range specification
- **Extensible**: Easy to add new document types and output formats
