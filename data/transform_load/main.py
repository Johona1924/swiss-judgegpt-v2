"""
Main orchestrator for document transformation and loading.

This script provides a unified interface for running different transformers
and managing the transformation pipeline.
"""

import sys
import argparse
from pathlib import Path
from typing import Optional
import os

from load_to_blob import BlobLoader, InteractiveBlobLoader
from base_transformers import (
    get_default_registry, 
    ConfigurationManager
)


def setup_transformers_from_config(config_path: Optional[str] = None):
    """Load and register transformers from configuration file."""
    # Make config path relative to script location if not absolute
    if config_path is None:
        script_dir = Path(__file__).parent
        config_path = script_dir / "config.json"
    elif not Path(config_path).is_absolute():
        script_dir = Path(__file__).parent
        config_path = script_dir / config_path
    
    config_manager = ConfigurationManager(str(config_path))
    registry = get_default_registry()
    
    transformer_configs = config_manager.config.get("transformers", {})
    
    for transformer_name, transformer_config in transformer_configs.items():
        try:
            # Dynamic import based on transformer name
            if transformer_name == "published_bger":
                from transform_published_bger import PublishedBgerTransformer
                transformer = PublishedBgerTransformer()
            elif transformer_name == "published_bger_trilingual":
                from transform_published_bger_trilingual import PublishedBgerTransformerTrilingual
                transformer = PublishedBgerTransformerTrilingual()
            else:
                print(f"Warning: Unknown transformer '{transformer_name}' in config. Add to setup_transformers_from_config to be usable.")
                continue
            
            registry.register_transformer(transformer_name, transformer)
            print(f"Registered transformer: {transformer_name}")
            
        except ImportError as e:
            print(f"Warning: Could not import transformer '{transformer_name}': {e}")
        except Exception as e:
            print(f"Error registering transformer '{transformer_name}': {e}")
    
    return config_manager


def run_batch_processing(
    transformer_name: str,
    connection_string: str,
    container_name: str,
    local_folder: str,
    file_range: Optional[str] = None,
    config_path: Optional[str] = None,
    batch_size: Optional[int] = None,
    max_workers: Optional[int] = None,
    max_retries: Optional[int] = None,
    use_individual_uploads: bool = False
) -> None:
    """
    Run batch processing with specified parameters.
    
    Args:
        transformer_name: Name of transformer to use
        connection_string: Azure Storage connection string
        container_name: Blob container name
        local_folder: Local folder containing files
        file_range: Optional range specification
        config_path: Optional configuration file path
    """
    config_manager = setup_transformers_from_config(config_path)
    
    # Get transformer
    registry = get_default_registry()
    transformer = registry.get_transformer(transformer_name)
    
    if not transformer:
        print(f"Error: Transformer '{transformer_name}' not found.")
        print(f"Available transformers: {registry.list_transformers()}")
        return
    
    # Get batch configuration from config file, then override with command line args
    blob_config = config_manager.config.get("blob_storage", {})
    final_batch_size = batch_size or blob_config.get("batch_size", 10)
    final_retry_attempts = max_retries or blob_config.get("retry_attempts", 3)
    final_max_workers = max_workers or blob_config.get("max_workers", 5)
    
    print(f"Using batch configuration: size={final_batch_size}, retries={final_retry_attempts}, workers={final_max_workers}")
    
    # Create loader with batch configuration
    loader = BlobLoader(
        connection_string=connection_string, 
        container_name=container_name,
        batch_size=final_batch_size,
        max_retries=final_retry_attempts,
        max_workers=final_max_workers
    )
    
    try:
        stats = loader.process_and_upload_files(
            local_folder=local_folder,
            transformer=transformer,
            file_extension=".md",
            file_range=file_range,
            ask_confirmation=False,
            use_batch_upload=not use_individual_uploads
        )
        
        if stats.failed_uploads == 0:
            print("✅ Batch processing completed successfully.")
        else:
            print(f"⚠️  Batch processing completed with {stats.failed_uploads} failures.")
            if stats.success_rate < 90:
                print("❌ High failure rate detected - check your connection and retry failed files.")
        
    except KeyboardInterrupt:
        print(f"\n⚠️  Operation cancelled by user (Ctrl+C)")
        print("🔄 You can resume by running the same command with a range parameter to skip processed files")
        sys.exit(130)  # Standard exit code for Ctrl+C
    except Exception as e:
        print(f"❌ Error during batch processing: {e}")
        sys.exit(1)


def run_interactive_mode(config_path: Optional[str] = None) -> None:
    """
    Run in interactive mode with user prompts.
    
    Args:
        config_path: Optional configuration file path
    """
    config_manager = setup_transformers_from_config(config_path)
    
    print("Document Transformation Pipeline")
    print("=" * 40)
    print(f"Working directory: {os.getcwd()}")
    print(f"Script directory: {Path(__file__).parent}")
    
    # Show available transformers
    registry = get_default_registry()
    transformers = registry.list_transformers()
    
    if not transformers:
        script_dir = Path(__file__).parent
        config_file = script_dir / "config.json"
        print(f"No transformers available.")
        print(f"Checked config file: {config_file}")
        print(f"Config file exists: {config_file.exists()}")
        return
    
    print(f"Available transformers: {', '.join(transformers)}")
    
    # Let user choose transformer
    transformer_name = input(f"Enter transformer name ({'/'.join(transformers)}): ").strip()
    
    # Get transformer
    transformer = registry.get_transformer(transformer_name)
    if not transformer:
        print(f"Error: Transformer '{transformer_name}' not found.")
        return
    
    print(f"Using transformer: {transformer_name}")
    
    # Create interactive loader and run
    loader = InteractiveBlobLoader.from_user_input()
    loader.interactive_process_files(transformer, file_extension=".md")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Document transformation and blob loading pipeline with batch upload support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode
  python main.py

  # Batch mode with default settings
  python main.py --batch --transformer published_bger_trilingual \\
    --connection-string "DefaultEndpointsProtocol=https;..." \\
    --container judgments --folder ./data/md_files

  # Batch mode with custom batch size and workers
  python main.py --batch --transformer published_bger_trilingual \\
    --connection-string "..." --container judgments \\
    --folder ./data --range "0:100" --batch-size 50 --max-workers 10

  # Use individual uploads (legacy mode)
  python main.py --batch --transformer published_bger \\
    --connection-string "..." --container judgments \\
    --folder ./data --individual-uploads

Note: Available transformers are defined in config.json
Batch settings can be configured in config.json or via command line arguments
        """
    )
    
    parser.add_argument(
        "--batch", 
        action="store_true",
        help="Run in batch mode (non-interactive)"
    )
    
    parser.add_argument(
        "--transformer",
        help="Name of transformer to use (required for batch mode)"
    )
    
    parser.add_argument(
        "--connection-string",
        help="Azure Storage connection string (required for batch mode)"
    )
    
    parser.add_argument(
        "--container",
        help="Blob container name (required for batch mode)"
    )
    
    parser.add_argument(
        "--folder",
        help="Local folder containing files (required for batch mode)"
    )
    
    parser.add_argument(
        "--range",
        help="File range specification (e.g., '100:200', ':100', '100:')"
    )
    
    parser.add_argument(
        "--config",
        help="Path to configuration file"
    )
    
    parser.add_argument(
        "--batch-size",
        type=int,
        help="Number of files to process in each batch (overrides config.json)"
    )
    
    parser.add_argument(
        "--max-workers",
        type=int,
        help="Maximum number of concurrent upload threads (overrides config.json)"
    )
    
    parser.add_argument(
        "--max-retries",
        type=int,
        help="Maximum number of retry attempts for failed uploads (overrides config.json)"
    )
    
    parser.add_argument(
        "--individual-uploads",
        action="store_true",
        help="Use individual uploads instead of batch processing"
    )
    
    args = parser.parse_args()
    
    if args.batch:
        # Validate required arguments for batch mode
        required_args = ["transformer", "connection_string", "container", "folder"]
        missing_args = [arg for arg in required_args if not getattr(args, arg)]
        
        if missing_args:
            print(f"Error: Missing required arguments for batch mode: {', '.join(missing_args)}")
            parser.print_help()
            sys.exit(1)
        
        run_batch_processing(
            transformer_name=args.transformer,
            connection_string=args.connection_string,
            container_name=args.container,
            local_folder=args.folder,
            file_range=args.range,
            config_path=args.config,
            batch_size=args.batch_size,
            max_workers=args.max_workers,
            max_retries=args.max_retries,
            use_individual_uploads=args.individual_uploads
        )
    else:
        run_interactive_mode(config_path=args.config)


if __name__ == "__main__":
    main()
