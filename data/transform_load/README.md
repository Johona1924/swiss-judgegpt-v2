# Document Transformation and Blob Loading Pipeline

Modular system for transforming documents and uploading them to Azure Blob Storage. Built for BGer judgment documents but extensible for other document types. **Features robust batch upload with concurrent processing and retry logic.**

## 🚀 Key Features

- **Batch Upload**: Concurrent uploads with configurable batch size and thread pool
- **Retry Logic**: Automatic retry with exponential backoff for failed uploads
- **Progress Tracking**: Real-time progress bars and comprehensive statistics
- **Error Resilience**: Failed uploads don't stop the entire batch
- **Configurable**: Centralized configuration with CLI overrides
- **Extensible**: Easy to add new transformers and document types

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure transformers in `config.json`:**
   ```json
   {
     "transformers": {
       "published_bger": { "description": "BGer judgments" },
       "published_bger_trilingual": { "description": "BGer trilingual" }
     },
     "blob_storage": {
       "batch_size": 50,
       "max_workers": 10,
       "retry_attempts": 3
     }
   }
   ```

3. **Run:**
   ```bash
   # Interactive mode
   python main.py
   
   # Batch mode with concurrent uploads
   python main.py --batch --transformer published_bger_trilingual \
     --connection-string "..." --container judgments --folder ./data
   ```

## Batch Upload Configuration

### Default Settings (config.json)
```json
{
  "blob_storage": {
    "batch_size": 50,        // Files processed concurrently
    "max_workers": 10,       // Thread pool size
    "retry_attempts": 3,     // Max retries per file
    "retry_delay_base": 2,   // Exponential backoff base
    "upload_timeout": 300    // Upload timeout in seconds
  }
}
```

### CLI Overrides
```bash
python main.py --batch \
  --batch-size 100 \
  --max-workers 20 \
  --max-retries 5 \
  --transformer published_bger_trilingual \
  --connection-string "..." \
  --container judgments \
  --folder ./data
```

## Usage

### Interactive Mode
```bash
python main.py
```
Prompts for transformer selection and Azure Storage details.

### Batch Mode
```bash
python main.py --batch \
  --transformer published_bger_trilingual \
  --connection-string "DefaultEndpointsProtocol=https;..." \
  --container judgments \
  --folder ./data/md_files \
  --range "0:100"
```

**Options:**
- `--transformer`: Name from config.json
- `--connection-string`: Azure Storage connection
- `--container`: Blob container name
- `--folder`: Local folder with files
- `--range`: Optional range (e.g., `"100:200"`, `":100"`, `"100:"`)
- `--config`: Custom config file path

## Adding Custom Transformers

### 1. Create Transformer Class
```python
# my_transformer.py
from base_transformers import BaseDocumentTransformer

class MyTransformer(BaseDocumentTransformer):
    def transform_document(self, content: str, filename: str) -> Dict[str, Any]:
        return {"title": "...", "content": content}
    
    def get_output_filename(self, input_filename: str) -> str:
        return input_filename.replace(".txt", ".json")
```

### 2. Add to config.json
```json
{
  "transformers": {
    "my_transformer": {
      "description": "My custom transformer"
    }
  }
}
```

### 3. Update main.py Import Logic
```python
elif transformer_name == "my_transformer":
    from my_transformer import MyTransformer
    transformer = MyTransformer()
```

## Available Transformers

- **`published_bger`**: Standard BGer judgments (single language)  
- **`published_bger_trilingual`**: BGer judgments with language-specific content fields

Both transformers expect filenames like `81 II 117.md` and markdown content with metadata.
