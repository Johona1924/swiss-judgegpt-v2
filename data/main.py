"""
Main orchestrator for document transformation and loading.

Command-line interface for running processors and uploading to Azure Blob Storage.
Supports configuration profiles for easier repeated usage.
"""

import sys
import argparse
import logging
from typing import Optional

from load_to_blob import BlobLoader
from document_processors import get_processor, list_processors
from config_loader import ConfigLoader, merge_config_with_args

# Configure root logging to see debug messages
logging.basicConfig(
    level=logging.WARNING,  # Set root level to WARNING to suppress Azure SDK logs
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Enable DEBUG logging only for your modules
logging.getLogger('load_to_blob').setLevel(logging.DEBUG)
logging.getLogger('config_loader').setLevel(logging.DEBUG)
logging.getLogger('core.validation').setLevel(logging.DEBUG)
# Note: document_processors modules don't currently use logging

# Suppress noisy Azure SDK loggers
#logging.getLogger('azure.core.pipeline.policies.http_logging_policy').setLevel(logging.WARNING)
#logging.getLogger('azure.storage.blob').setLevel(logging.WARNING)
#logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)


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
    # Load configuration system
    config_loader = ConfigLoader()
    
    parser = argparse.ArgumentParser(
        description="Document transformation and blob loading pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  # Using a configuration profile (recommended)
  python main.py --profile dev --folder ./data/md_files

  # Override profile settings
  python main.py --profile prod --batch-size 50 --max-workers 10

  # Traditional usage (all arguments required)
  python main.py --processor published_bger_trilingual \\
    --connection-string "DefaultEndpointsProtocol=https;..." \\
    --container judgments --folder ./data/md_files

Available processors: {', '.join(list_processors())}
Available profiles: {', '.join(config_loader.list_profiles()) if config_loader.list_profiles() else 'None (create configs.yaml)'}
        """
    )
    
    # Profile argument (optional)
    parser.add_argument(
        "--profile",
        help="Configuration profile to use (from configs.yaml)"
    )
    
    # Required arguments (but optional when using profiles)
    parser.add_argument(
        "--processor",
        help="Name of processor to use"
    )
    
    parser.add_argument(
        "--connection-string",
        help="Azure Storage connection string"
    )
    
    parser.add_argument(
        "--container",
        help="Blob container name"
    )
    
    parser.add_argument(
        "--folder",
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
    
    # Handle configuration
    if args.profile:
        # Load profile configuration
        try:
            profile_config = config_loader.get_profile_config(args.profile)
            print(f"📋 Using profile: {args.profile}")
        except ValueError as e:
            print(e)
            sys.exit(1)
        
        # Merge profile config with CLI args
        final_config = merge_config_with_args(profile_config, args)
    else:
        # Traditional mode - convert args to config dict
        final_config = {
            "processor": args.processor,
            "connection_string": args.connection_string,
            "container": args.container,
            "folder": args.folder,
            "range": args.range,
            "batch_size": args.batch_size,
            "max_workers": args.max_workers,
            "max_retries": args.max_retries,
            "individual_uploads": args.individual_uploads,
            "skip_validation": args.skip_validation
        }
    
    # Validate required parameters
    required_params = ["processor", "container", "folder", "connection_string"]
    missing_params = [param for param in required_params if not final_config.get(param)]
    
    if missing_params:
        print(f"❌ Missing required parameters: {', '.join(missing_params)}")
        if args.profile:
            print(f"   Profile '{args.profile}' doesn't provide these values and they weren't specified via CLI")
        else:
            print("   Please provide these via command line arguments or use a configuration profile")
        sys.exit(1)
    
    run_processing(
        processor_name=final_config["processor"],
        connection_string=final_config["connection_string"],
        container_name=final_config["container"],
        local_folder=final_config["folder"],
        file_range=final_config.get("range"),
        batch_size=final_config.get("batch_size", 10),
        max_workers=final_config.get("max_workers", 5),
        max_retries=final_config.get("max_retries", 3),
        use_individual_uploads=final_config.get("individual_uploads", False),
        skip_validation=final_config.get("skip_validation", False)
    )


if __name__ == "__main__":
    main()
