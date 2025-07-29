"""
Azure Blob Storage loader for document transformation pipeline.

This module provides utilities for uploading JSON documents to Azure Blob Storage
with support for batch processing, range selection, progress tracking, and JSON schema validation.
"""

import os
import json
import traceback
import time
import concurrent.futures
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.core.exceptions import ResourceExistsError, AzureError
from tqdm import tqdm

try:
    from jsonschema import validate, ValidationError, Draft7Validator
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False
    ValidationError = Exception  # Fallback for type hints
    Draft7Validator = None  # Fallback for type hints

from core.types import DocumentTransformer
from core.validation import validate_document, ValidationResult


@dataclass
class UploadResult:
    """Result of a blob upload operation."""
    blob_name: str
    success: bool
    error: Optional[str] = None
    retry_count: int = 0


@dataclass
class BatchUploadStats:
    """Statistics for batch upload operations."""
    total_files: int
    successful_uploads: int
    failed_uploads: int
    total_size_mb: float
    duration_seconds: float
    
    @property
    def success_rate(self) -> float:
        return (self.successful_uploads / self.total_files) * 100 if self.total_files > 0 else 0


class BlobLoader:
    """
    Loader for uploading JSON documents to Azure Blob Storage.
    Supports batch upload operations with retry logic and progress tracking.
    """
    
    def __init__(
        self, 
        connection_string: str, 
        container_name: str,
        batch_size: int = 10,
        max_retries: int = 3,
        max_workers: int = 5
    ):
        """
        Initialize the BlobLoader.
        
        Args:
            connection_string: Azure Storage connection string
            container_name: Name of the blob container
            batch_size: Number of files to process in each batch
            max_retries: Maximum number of retry attempts for failed uploads
            max_workers: Maximum number of concurrent upload threads
        """
        self.connection_string = connection_string
        self.container_name = container_name
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.max_workers = max_workers
        self._container_client = None
    
    @property
    def container_client(self):
        """Lazy initialization of container client."""
        if self._container_client is None:
            self._container_client = self._connect_blob_service()
        return self._container_client
    
    def _connect_blob_service(self):
        """Connect to Azure Blob Storage and create container if needed."""
        blob_service = BlobServiceClient.from_connection_string(self.connection_string)
        container = blob_service.get_container_client(self.container_name)
        
        try:
            container.create_container()
            print(f"Created container '{self.container_name}'")
        except ResourceExistsError:
            # Container already exists
            pass
        
        return container
    
    def upload_json_document(self, blob_name: str, json_data: str) -> UploadResult:
        """
        Upload a JSON document to blob storage with retry logic.
        
        Args:
            blob_name: Name of the blob
            json_data: JSON string to upload
            
        Returns:
            UploadResult with success status and error details
        """
        content_settings = ContentSettings(
            content_type="application/json",
            content_encoding="UTF-8"
        )
        
        for attempt in range(self.max_retries + 1):
            try:
                self.container_client.upload_blob(
                    name=blob_name,
                    data=json_data,
                    overwrite=True,
                    content_settings=content_settings
                )
                return UploadResult(blob_name=blob_name, success=True, retry_count=attempt)
                
            except Exception as e:
                if attempt == self.max_retries:
                    return UploadResult(
                        blob_name=blob_name, 
                        success=False, 
                        error=str(e), 
                        retry_count=attempt
                    )
                
                # Exponential backoff
                wait_time = (2 ** attempt) + (0.1 * attempt)
                time.sleep(wait_time)
    
    def batch_upload_documents(
        self, 
        documents: List[Tuple[str, str]]
    ) -> Tuple[List[UploadResult], BatchUploadStats]:
        """
        Upload multiple documents using concurrent batch processing.
        
        Args:
            documents: List of (blob_name, json_data) tuples
            
        Returns:
            Tuple of (upload_results, batch_stats)
        """
        start_time = time.time()
        upload_results: List[UploadResult] = []
        total_size_bytes = sum(len(data.encode('utf-8')) for _, data in documents)
        
        try:
            # Process documents in batches with concurrent uploads
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                
                # Submit all upload tasks
                future_to_document = {
                    executor.submit(self.upload_json_document, blob_name, json_data): (blob_name, json_data)
                    for blob_name, json_data in documents
                }
                
                # Collect results with progress bar
                with tqdm(total=len(documents), desc="Uploading", unit="files") as pbar:
                    try:
                        for future in concurrent.futures.as_completed(future_to_document):
                            result = future.result()
                            upload_results.append(result)
                            pbar.update(1)
                            
                            # Update progress bar description with success/failure
                            successful = sum(1 for r in upload_results if r.success)
                            failed = len(upload_results) - successful
                            pbar.set_postfix(success=successful, failed=failed)
                    except KeyboardInterrupt:
                        print(f"\n⚠️  Keyboard interrupt detected. Cancelling remaining uploads...")
                        
                        # Cancel remaining futures
                        for future in future_to_document:
                            future.cancel()
                        
                        # Wait a bit for cancellations to take effect
                        time.sleep(0.5)
                        
                        # Add failed results for cancelled uploads
                        completed_blobs = {r.blob_name for r in upload_results}
                        for blob_name, _ in documents:
                            if blob_name not in completed_blobs:
                                upload_results.append(UploadResult(
                                    blob_name=blob_name,
                                    success=False,
                                    error="Cancelled by user",
                                    retry_count=0
                                ))
                        
                        print(f"📊 Cancelled after processing {len([r for r in upload_results if r.success])} files successfully")
                        # Re-raise to be caught by outer exception handler
                        raise
        
        except KeyboardInterrupt:
            print(f"\n⚠️  Operation cancelled by user")
            # Create minimal stats for cancelled operation
            successful_uploads = sum(1 for r in upload_results if r.success)
            failed_uploads = len(upload_results) - successful_uploads
            duration = time.time() - start_time
            
            return upload_results, BatchUploadStats(
                total_files=len(documents),
                successful_uploads=successful_uploads,
                failed_uploads=failed_uploads,
                total_size_mb=total_size_bytes / (1024 * 1024),
                duration_seconds=duration
            )
        
        # Calculate statistics
        duration = time.time() - start_time
        successful_uploads = sum(1 for r in upload_results if r.success)
        failed_uploads = len(upload_results) - successful_uploads
        
        stats = BatchUploadStats(
            total_files=len(documents),
            successful_uploads=successful_uploads,
            failed_uploads=failed_uploads,
            total_size_mb=total_size_bytes / (1024 * 1024),
            duration_seconds=duration
        )
        
        return upload_results, stats
    
    def process_and_upload_files(
        self,
        local_folder: str,
        transformer: DocumentTransformer,
        file_extension: str = ".md",
        file_range: Optional[str] = None,
        use_batch_upload: bool = True,
        validate_schema: bool = True
    ) -> BatchUploadStats:
        """
        Process files from a local folder and upload them to blob storage.
        
        Args:
            local_folder: Path to the local folder containing files
            transformer: Document transformer implementing the DocumentTransformer protocol
            file_extension: File extension to filter by (default: ".md")
            file_range: Range specification like "100:200", ":100", "100:", or None for all
            use_batch_upload: Whether to use batch upload (True) or individual uploads (False)
            validate_schema: Whether to validate documents against JSON schema before upload
            
        Returns:
            BatchUploadStats with upload statistics
        """
        try:
            self._validate_local_folder(local_folder, file_extension)
            files = self._get_files_in_range(local_folder, file_extension, file_range)
            
            # Validate transformer schema availability upfront if validation is enabled
            if validate_schema:
                self._validate_transformer_schema_available(transformer)
            
            # Show upload details and ask for confirmation
            self._ask_upload_confirmation(files, local_folder)
            
            print(f"🚀 Starting processing of {len(files)} files...")
            if validate_schema:
                print("🔍 Schema validation: ENABLED")
            else:
                print("⚠️  Schema validation: DISABLED")
            
            if use_batch_upload:
                return self._process_files_batch(files, local_folder, transformer, validate_schema)
            else:
                return self._process_files_individual(files, local_folder, transformer, validate_schema)
            
        except Exception as e:
            print(f"ERROR during processing: {e}")
            traceback.print_exc()
            # Return empty stats on error
            return BatchUploadStats(0, 0, 0, 0.0, 0.0)
    
    def _validate_local_folder(self, local_folder: str, file_extension: str) -> None:
        """Validate that the local folder exists and contains files."""
        if not os.path.exists(local_folder):
            raise FileNotFoundError(f"The folder '{local_folder}' does not exist.")
        
        if not any(f.endswith(file_extension) for f in os.listdir(local_folder)):
            raise ValueError(f"The folder '{local_folder}' does not contain any {file_extension} files.")
    
    def _get_files_in_range(
        self, 
        local_folder: str, 
        file_extension: str, 
        file_range: Optional[str]
    ) -> List[str]:
        """Get files filtered by extension and optional range."""
        all_files = sorted([
            f for f in os.listdir(local_folder) 
            if f.endswith(file_extension)
        ])
        
        if not file_range:
            return all_files
        
        return self._apply_range_filter(all_files, file_range)
    
    def _apply_range_filter(self, files: List[str], range_spec: str) -> List[str]:
        """Apply range filter to file list."""
        if not range_spec.strip():
            return files
        
        range_parts = range_spec.split(":")
        if len(range_parts) != 2:
            raise ValueError(f"Invalid range expression: {range_spec}")
        
        start_str, end_str = range_parts
        start_index = int(start_str) if start_str.strip().isdigit() else 0
        end_index = int(end_str) if end_str.strip().isdigit() else len(files)
        
        filtered_files = files[start_index:end_index]
        if not filtered_files:
            raise ValueError("No files found in the specified range.")
        
        return filtered_files
    
    def _validate_transformer_schema_available(self, transformer: DocumentTransformer) -> None:
        """
        Validate that transformer has a valid JSON schema when validation is required.
        
        Args:
            transformer: Transformer that should have a schema
            
        Raises:
            ValueError: If no schema is available or schema is invalid when validation is required
        """
        transformer_name = getattr(transformer, 'NAME', transformer.__class__.__name__)
        
        # Check if transformer has SCHEMA attribute
        if not hasattr(transformer, 'SCHEMA') or not transformer.SCHEMA:
            raise ValueError(
                f"❌ Schema validation is enabled but transformer '{transformer_name}' "
                f"has no SCHEMA attribute or it's empty.\n"
                f"   To fix this:\n"
                f"   • Add a SCHEMA attribute to the transformer class, OR\n"
                f"   • Use --skip-validation to disable schema validation"
            )
        
        # Check if jsonschema library is available
        if not JSONSCHEMA_AVAILABLE:
            raise ValueError(
                f"❌ Schema validation is enabled but 'jsonschema' library is not installed.\n"
                f"   To fix this:\n"
                f"   • Install jsonschema: pip install jsonschema, OR\n"
                f"   • Use --skip-validation to disable schema validation"
            )
        
        # Validate that the schema itself is a valid JSON schema
        try:
            Draft7Validator.check_schema(transformer.SCHEMA)
        except Exception as e:
            raise ValueError(
                f"❌ Schema validation is enabled but transformer '{transformer_name}' "
                f"has an invalid JSON schema.\n"
                f"   Schema error: {str(e)}\n"
                f"   To fix this:\n"
                f"   • Fix the SCHEMA attribute in the transformer class, OR\n"
                f"   • Use --skip-validation to disable schema validation"
            )
    
    def _validate_document_schema(self, document: Dict[str, Any], transformer: DocumentTransformer, filename: str) -> bool:
        """
        Validate document against transformer's schema.
        
        Args:
            document: Document to validate
            transformer: Transformer that created the document
            filename: Original filename for error reporting
            
        Returns:
            True if valid, False if validation fails
            
        Note:
            This method assumes schema availability has already been checked
            by _validate_transformer_schema_available when validation is enabled.
        """
        schema = transformer.SCHEMA
        validation_result = validate_document(document, schema)
        
        if validation_result.is_valid:
            return True
        
        print(f"❌ Schema validation failed for '{filename}':")
        for error in validation_result.errors:
            print(f"   • {error}")
        
        return False
    
    def _ask_upload_confirmation(self, files: List[str], local_folder: str) -> None:
        """Ask user for confirmation before processing and uploading."""
        print(f"\n📋 Upload Summary:")
        print(f"   📁 Source folder: {local_folder}")
        print(f"   ☁️  Target container: {self.container_name}")
        print(f"   📄 Files to process: {len(files)}")
        print(f"   🔧 Upload method: {'Batch upload' if self.batch_size > 1 else 'Individual upload'}")
        
        if len(files) <= 10:
            print(f"   📝 File list:")
            for file in files:
                print(f"      - {file}")
        else:
            print(f"   📝 First 5 files:")
            for file in files[:5]:
                print(f"      - {file}")
            print(f"      ... and {len(files) - 5} more files")
        
        print(f"\n⚠️  This will upload {len(files)} files to Azure Blob Storage.")
        confirm = input("Do you want to proceed? (yes/no): ").strip().lower()
        
        if confirm not in ["yes", "y"]:
            print("❌ Operation cancelled by user.")
            raise SystemExit(0)
    
    def _process_files_batch(
        self, 
        files: List[str], 
        local_folder: str, 
        transformer: DocumentTransformer,
        validate_schema: bool = True
    ) -> BatchUploadStats:
        """Process and batch upload files using the provided transformer."""
        print(f"Processing {len(files)} files in batches of {self.batch_size}...")
        
        # Transform all files first
        documents: List[Tuple[str, str]] = []
        
        try:
            with tqdm(files, desc="Transforming", unit="files") as pbar:
                for filename in pbar:
                    file_path = os.path.join(local_folder, filename)
                    
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                        
                        # Transform the document
                        json_obj = transformer.transform_document(content, filename)
                        
                        # Get output filename
                        output_filename = transformer.get_output_filename(filename)
                        
                        # Add metadata
                        json_obj["filename"] = output_filename
                        json_obj["last_updated"] = datetime.now(timezone.utc).isoformat(
                            sep="T", timespec="seconds"
                        )
                        
                        # Validate against schema if requested
                        if validate_schema and not self._validate_document_schema(json_obj, transformer, filename):
                            print(f"⚠️  Skipping '{filename}' due to validation errors")
                            continue
                        
                        # Serialize to JSON
                        json_str = json.dumps(json_obj, ensure_ascii=False)
                        documents.append((output_filename, json_str))
                        
                    except Exception as e:
                        print(f"\nError processing file '{filename}': {e}")
                        # Continue with other files
        except KeyboardInterrupt:
            print(f"\n⚠️  Transformation cancelled by user. Processed {len(documents)} files.")
            if not documents:
                print("📊 No files were transformed. Exiting.")
                return BatchUploadStats(0, 0, 0, 0.0, 0.0)
            
            proceed = input("Upload the files that were already transformed? (y/n): ").strip().lower()
            if proceed != 'y':
                print("📊 Operation cancelled. No files uploaded.")
                return BatchUploadStats(len(documents), 0, len(documents), 0.0, 0.0)
        
        # Batch upload all documents
        upload_results, stats = self.batch_upload_documents(documents)
        
        # Report failed uploads
        failed_uploads = [r for r in upload_results if not r.success]
        if failed_uploads:
            print(f"\nFailed uploads ({len(failed_uploads)}):")
            for result in failed_uploads:
                print(f"  - {result.blob_name}: {result.error}")
        
        # Print summary statistics
        print(f"\n📊 Batch Upload Summary:")
        print(f"  Total files: {stats.total_files}")
        print(f"  Successful: {stats.successful_uploads}")
        print(f"  Failed: {stats.failed_uploads}")
        print(f"  Success rate: {stats.success_rate:.1f}%")
        print(f"  Total size: {stats.total_size_mb:.2f} MB")
        print(f"  Duration: {stats.duration_seconds:.2f} seconds")
        if stats.duration_seconds > 0:
            throughput = stats.total_size_mb / stats.duration_seconds
            print(f"  Throughput: {throughput:.2f} MB/s")
        
        return stats
    
    def _process_files_individual(
        self, 
        files: List[str], 
        local_folder: str, 
        transformer: DocumentTransformer,
        validate_schema: bool = True
    ) -> BatchUploadStats:
        """Process and upload files individually (legacy mode)."""
        start_time = time.time()
        successful_uploads = 0
        failed_uploads = 0
        total_size_bytes = 0
        
        for filename in tqdm(files, desc="Processing"):
            file_path = os.path.join(local_folder, filename)
            
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Transform the document
                json_obj = transformer.transform_document(content, filename)
                
                # Get output filename
                output_filename = transformer.get_output_filename(filename)
                
                # Add metadata
                json_obj["filename"] = output_filename
                json_obj["last_updated"] = datetime.now(timezone.utc).isoformat(
                    sep="T", timespec="seconds"
                )
                
                # Validate against schema if requested
                if validate_schema and not self._validate_document_schema(json_obj, transformer, filename):
                    failed_uploads += 1
                    continue
                
                # Serialize and upload
                json_str = json.dumps(json_obj, ensure_ascii=False)
                total_size_bytes += len(json_str.encode('utf-8'))
                
                result = self.upload_json_document(output_filename, json_str)
                if result.success:
                    successful_uploads += 1
                else:
                    failed_uploads += 1
                    print(f"Failed to upload '{filename}': {result.error}")
                
            except Exception as e:
                failed_uploads += 1
                print(f"Error processing file '{filename}': {e}")
        
        duration = time.time() - start_time
        return BatchUploadStats(
            total_files=len(files),
            successful_uploads=successful_uploads,
            failed_uploads=failed_uploads,
            total_size_mb=total_size_bytes / (1024 * 1024),
            duration_seconds=duration
        )
