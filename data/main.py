"""
Main orchestrator for document transformation and loading.

Command-line interface for running processors and uploading to Azure Blob Storage.
All arguments must be provided via command line - no interactive mode.
"""

import sys
import argparse
from typing import Optional

from load_to_blob import BlobLoader
from document_processors import get_processor, list_processors


def run_processing(
    processor_name: str,
    connection_string: str,
    container_name: str,
    local_folder: str,
    file_range: Optional[str] = None,
    batch_size: int = 10,
    max_workers: int = 5,
    max_retries: int = 3,
    use_individual_uploads: bool = False,
    skip_validation: bool = False
) -> None:
    """Run document processing and upload."""
    
    # Get processor
    processor = get_processor(processor_name)
    if not processor:
        print(f"❌ Error: processor '{processor_name}' not found.")
        print(f"Available processors: {', '.join(list_processors())}")
        sys.exit(1)
    
    print(f"🔧 Using processor: {processor_name}")
    print(f"📦 Batch configuration: size={batch_size}, retries={max_retries}, workers={max_workers}")
    print(f"📁 Processing files from: {local_folder}")
    print(f"☁️  Uploading to container: {container_name}")
    print(f"ℹ️  You will be asked to confirm before uploading.")
    
    # Create loader
    loader = BlobLoader(
        connection_string=connection_string,
        container_name=container_name,
        batch_size=batch_size,
        max_retries=max_retries,
        max_workers=max_workers
    )
    
    try:
        stats = loader.process_and_upload_files(
            local_folder=local_folder,
            processor=processor,
            file_extension=".md",
            file_range=file_range,
            use_batch_upload=not use_individual_uploads,
            validate_schema=not skip_validation
        )
        
        print(f"\n📊 Processing Summary:")
        print(f"   Total files: {stats.total_files}")
        print(f"   Successful: {stats.successful_uploads}")
        print(f"   Failed: {stats.failed_uploads}")
        print(f"   Success rate: {stats.success_rate:.1f}%")
        print(f"   Total size: {stats.total_size_mb:.2f} MB")
        print(f"   Duration: {stats.duration_seconds:.2f} seconds")
        
        if stats.failed_uploads == 0:
            print("✅ All files processed successfully!")
        else:
            print(f"⚠️  {stats.failed_uploads} files failed to process.")
            if stats.success_rate < 90:
                print("❌ High failure rate detected - check your connection and retry.")
                sys.exit(1)
        
    except KeyboardInterrupt:
        print(f"\n⚠️  Operation cancelled by user (Ctrl+C)")
        print("🔄 You can resume by using a range parameter to skip processed files")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Error during processing: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Document transformation and blob loading pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  # Process all files with default settings (includes validation)
  python main.py --processor published_bger_trilingual \\
    --connection-string "DefaultEndpointsProtocol=https;..." \\
    --container judgments --folder ./data/md_files

  # Process with custom settings and file range
  python main.py --processor published_bger \\
    --connection-string "..." --container judgments \\
    --folder ./data --range "0:100" --batch-size 50 --max-workers 10

  # Skip schema validation (not recommended)
  python main.py --processor published_bger \\
    --connection-string "..." --container judgments \\
    --folder ./data --skip-validation

Available processors: {', '.join(list_processors())}
        """
    )
    
    # Required arguments
    parser.add_argument(
        "--processor",
        required=True,
        help="Name of processor to use"
    )
    
    parser.add_argument(
        "--connection-string",
        required=True,
        help="Azure Storage connection string"
    )
    
    parser.add_argument(
        "--container",
        required=True,
        help="Blob container name"
    )
    
    parser.add_argument(
        "--folder",
        required=True,
        help="Local folder containing files to process"
    )
    
    # Optional arguments
    parser.add_argument(
        "--range",
        help="File range specification (e.g., '100:200', ':100', '100:')"
    )
    
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of files to process in each batch (default: 10)"
    )
    
    parser.add_argument(
        "--max-workers",
        type=int,
        default=5,
        help="Maximum number of concurrent upload threads (default: 5)"
    )
    
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum number of retry attempts for failed uploads (default: 3)"
    )
    
    parser.add_argument(
        "--individual-uploads",
        action="store_true",
        help="Use individual uploads instead of batch processing"
    )
    
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip JSON schema validation before upload (not recommended)"
    )
    
    args = parser.parse_args()
    
    run_processing(
        processor_name=args.processor,
        connection_string=args.connection_string,
        container_name=args.container,
        local_folder=args.folder,
        file_range=args.range,
        batch_size=args.batch_size,
        max_workers=args.max_workers,
        max_retries=args.max_retries,
        use_individual_uploads=args.individual_uploads,
        skip_validation=args.skip_validation
    )


if __name__ == "__main__":
    main()
