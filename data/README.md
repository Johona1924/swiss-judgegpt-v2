# Document Transformation Pipeline

A lean, streamlined system for transforming documents and uploading them to Azure Blob Storage.
Supports configuration profiles to avoid repeatedly entering connection strings and other parameters.

## Project Structure

```
transform_load/
├── main.py                     # CLI interface and orchestration
├── load_to_blob.py            # Azure Blob Storage upload logic
├── config_loader.py           # Configuration management
├── configs.yaml               # Configuration profiles
├── .env                       # Environment variables (gitignored)
├── .env.example              # Template for .env
├── requirements.txt           # Dependencies
├── README.md                  # This file
├── core/
│   ├── types.py              # Protocol definitions and utilities
│   └── validation.py         # JSON schema validation
├── document_processors/
│   ├── __init__.py           # Processor registry
│   ├── published_bger.py     # BGer judgment processor (monolingual)
│   └── published_bger_trilingual.py  # BGer processor (trilingual)
└── schemas/
    ├── published_bger.py     # JSON schema for BGer judgments
    └── published_bger_trilingual.py  # JSON schema for trilingual BGer
```

## Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment variables**:
   ```bash
   # Copy the example file
   cp .env.example .env
   
   # Edit .env and add a valid Azure Storage connection string
   # CONNECTION_STRING_TEST="DefaultEndpointsProtocol=https;..."
   ```

3. **Create configuration profiles** (see Configuration section below)

## Usage

### Using Configuration Profiles (Recommended)

Create profiles in `configs.yaml` to avoid repeatedly entering the same parameters:

```bash
# Use a predefined profile
python main.py --profile dev

# Override specific profile settings
python main.py --profile prod --folder ./raw_data/bger-data --batch-size 50 --max-workers 10
```

### Traditional Usage

You can still provide all arguments via command line:

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
    --processor published_bger \
    --connection-string "..." \
    --container judgments \
    --folder ./data \
    --individual-uploads

# Skip JSON schema validation (not recommended)
python main.py \
    --processor published_bger \
    --connection-string "..." \
    --container judgments \
    --folder ./data \
    --skip-validation
```

### Confirmation Step

Before any files are processed or uploaded, you'll be asked to confirm.

Type `yes` or `y` to proceed, anything else will cancel the operation.

## Configuration

### Configuration Profiles

Create a `configs.yaml` file to define reusable configuration profiles. Example:

```yaml
# Testing profile
test:
  processor: "published_bger"
  connection_string: "CONNECTION_STRING_TEST"  # References environment variable
  container: "judgments-test"
  batch_size: 2
  max_workers: 1
  max_retries: 1
  skip_validation: false
```

### Environment Variables

Store sensitive information in a `.env` file:

```bash
# Environment-specific connection strings
CONNECTION_STRING_DEV="DefaultEndpointsProtocol=https;AccountName=devaccount;AccountKey=devkey;EndpointSuffix=core.windows.net"
CONNECTION_STRING_TEST="DefaultEndpointsProtocol=https;AccountName=testaccount;AccountKey=testkey;EndpointSuffix=core.windows.net"
```

### Priority Order

CLI arguments have the highest priority and can override any profile settings.

## Command Line Options

### Profile Arguments
- `--profile`: Configuration profile to use (from `configs.yaml`)

### Required Arguments (when not using profiles)
- `--processor`: Name of processor to use (`published_bger` or `published_bger_trilingual`)
- `--connection-string`: Azure Storage connection string (can be set via environment variable)
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
- **Optional skip**: Use `--skip-validation` to bypass validation for troubleshooting

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