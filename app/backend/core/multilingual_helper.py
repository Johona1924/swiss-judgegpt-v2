"""
Multilingual Search Validation Helper

Provides validation functions for multilingual search configuration
to ensure the app fails fast if configuration is invalid.
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

from azure.search.documents.indexes.aio import SearchIndexClient

logger = logging.getLogger(__name__)


def validate_multilingual_search_config(
    enable_multilingual: bool,
    content_language: Optional[str],
    app_logger=None
) -> None:
    """
    Validate multilingual search configuration early at startup.
    This ensures the app fails fast if configuration is invalid.
    
    Note: This is now a synchronous function that only validates environment
    variables and prompt file structure. Index schema validation happens
    later during the first search request.
    
    Args:
        enable_multilingual: Whether multilingual search is enabled
        content_language: Content language for monolingual mode
        app_logger: Optional app logger to use for output
        
    Raises:
        ValueError: If configuration is invalid
    """
    # Use app logger if provided, otherwise fall back to module logger
    log = app_logger if app_logger else logger
    
    if enable_multilingual:
        log.info("ENABLE_MULTILINGUAL_SEARCH is true, validating multilingual configuration")
        _validate_multilingual_prompt_files(log)
    else:
        log.info("ENABLE_MULTILINGUAL_SEARCH is false, validating monolingual configuration")
        _validate_monolingual_mode_sync(content_language, log)


def _validate_multilingual_prompt_files(log=None) -> None:
    """
    Validate that multilingual prompt files exist..
    This is a synchronous check that only validates file structure.
    """
    log = log if log else logger
    
    prompt_base_path = Path("approaches/prompts/MULTILINGUAL")
    if not prompt_base_path.exists():
        raise ValueError(
            "Multilingual search enabled but no MULTILINGUAL prompt directory found. "
            "Please create 'approaches/prompts/MULTILINGUAL' with the required prompt files."
        )
    
    # Find valid multilingual directories
    supported_languages = get_supported_languages()
    if not supported_languages:
        raise ValueError(
            "Multilingual search enabled but no valid multilingual prompt directories found. "
            "Please create a directory like 'MULTILINGUAL/DE_FR_IT' with the required prompt files."
        )
    
    log.info(f"✅ Multilingual prompt files validated for languages: {supported_languages}")


def _validate_monolingual_mode_sync(content_language: Optional[str], log=None) -> None:
    """Validate monolingual mode requirements synchronously"""
    log = log if log else logger
    
    if not content_language:
        raise ValueError(
            "Monolingual search mode requires CONTENT_LANGUAGE environment variable to be set. "
            "Example: CONTENT_LANGUAGE=de"
        )
    
    # Check for corresponding prompt files
    _validate_prompt_files_monolingual(content_language, log)
    
    log.info(f"✅ Monolingual prompt files validated for language: {content_language}")


async def validate_index_schema(
    enable_multilingual: bool,
    search_endpoint: str,
    search_index: str,
    azure_credential,
    log=None
) -> None:
    """
    Validate the search index schema. This is called asynchronously
    during the first search request, not during app startup.
    
    Args:
        enable_multilingual: Whether multilingual search is enabled
        search_endpoint: Azure Search service endpoint
        search_index: Azure Search index name
        azure_credential: Azure credential for authentication
        log: Logger to use for output
        
    Raises:
        ValueError: If index schema is invalid
    """
    log = log if log else logger
    
    if enable_multilingual:
        await _validate_multilingual_index_schema(search_endpoint, search_index, azure_credential, log)
    else:
        await _validate_monolingual_index_schema(search_endpoint, search_index, azure_credential, log)


async def _validate_multilingual_index_schema(search_endpoint: str, search_index: str, azure_credential, log=None) -> None:
    """Validate multilingual mode index schema requirements"""
    log = log if log else logger
    search_index_client = SearchIndexClient(
        endpoint=search_endpoint,
        credential=azure_credential
    )
    
    try:
        index = await search_index_client.get_index(search_index)
        fields = {field.name: field for field in index.fields}
        
        # Check for language field
        language_field = None
        for candidate in ['language', 'lang', 'locale']:
            if candidate in fields and fields[candidate].filterable:
                language_field = candidate
                break
        
        if not language_field:
            raise ValueError(
                "Multilingual search enabled but no filterable language field found in index schema. "
                "Required: 'language', 'lang', or 'locale' field that is filterable."
            )
        
        # Check for language-specific content fields
        content_field_pattern = re.compile(r'^content_([a-z]{2})$')
        language_content_fields = {}
        supported_languages = []
        
        for field_name in fields:
            match = content_field_pattern.match(field_name)
            if match and fields[field_name].searchable:
                language_code = match.group(1)
                language_content_fields[language_code] = field_name
                supported_languages.append(language_code)
        
        if len(language_content_fields) < 1:
            raise ValueError(
                "Multilingual search enabled but no language-specific content fields found in index schema. "
                "Required: 'content_{lang}' fields (e.g., content_de, content_fr, content_it) that are searchable."
            )
        
        log.info(
            f"✅ Multilingual index schema validated successfully. "
            f"Languages: {supported_languages}, Language field: {language_field}"
        )
        
    finally:
        await search_index_client.close()


async def _validate_monolingual_index_schema(search_endpoint: str, search_index: str, azure_credential, log=None) -> None:
    """Validate monolingual mode index schema requirements"""
    log = log if log else logger
    search_index_client = SearchIndexClient(
        endpoint=search_endpoint,
        credential=azure_credential
    )
    
    try:
        index = await search_index_client.get_index(search_index)
        fields = {field.name: field for field in index.fields}
        
        if 'content' not in fields or not fields['content'].searchable:
            raise ValueError(
                "Monolingual search mode requires a searchable 'content' field in the index schema."
            )
        
        log.info("✅ Monolingual index schema validated successfully. Content field: content")
        
    finally:
        await search_index_client.close()

def _validate_prompt_files_monolingual(content_language: str, log=None) -> None:
    """Validate that monolingual prompt files exist for the specified language"""
    log = log if log else logger
    lang_upper = content_language.upper()
    prompt_base_path = Path("approaches/prompts")
    monolingual_prompt_dir = prompt_base_path / "MONOLINGUAL" / lang_upper
    
    if not monolingual_prompt_dir.exists():
        raise ValueError(
            f"Monolingual search mode enabled but prompt directory not found: {monolingual_prompt_dir}. "
            f"Please create this directory with the required prompt files for language: {content_language}"
        )
    
    # Check for required prompt files
    required_files = [
        f"chat_query_rewrite_{content_language.lower()}.prompty",
        f"chat_query_rewrite_tools_{content_language.lower()}.json"
    ]
    
    missing_files = []
    for file_name in required_files:
        file_path = monolingual_prompt_dir / file_name
        if not file_path.exists():
            missing_files.append(str(file_path))
    
    if missing_files:
        raise ValueError(
            f"Monolingual search mode enabled but missing prompt files: {missing_files}. "
            f"Please create these files for language: {content_language}"
        )


def get_supported_languages() -> list[str]:
    """
    Get list of supported languages by scanning existing multilingual prompt directories.
    Returns empty list if no multilingual directories found.
    """
    prompt_base_path = Path("approaches/prompts/MULTILINGUAL")
    if not prompt_base_path.exists():
        return []
    
    for dir_path in prompt_base_path.iterdir():
        if dir_path.is_dir():
            # Check if this directory has the required files
            languages = dir_path.name.lower().split('_')
            base_name = "_".join(languages)
            
            prompty_file = prompt_base_path / dir_path.name / f"chat_query_rewrite_{base_name}.prompty"
            tools_file = prompt_base_path / dir_path.name / f"chat_query_rewrite_tools_{base_name}.json"
            
            # Check if files exist
            if prompty_file.exists() and tools_file.exists():
                return [lang.lower() for lang in languages]
    
    return []


def get_multilingual_prompt_files() -> tuple[str, str]:
    """
    Get the multilingual prompt file paths.
    Returns (prompty_file, tools_file) relative paths.
    """
    supported_languages = get_supported_languages()
    if not supported_languages:
        raise ValueError("No multilingual prompt directories found")
    
    sorted_languages = sorted(supported_languages)
    folder_name = "_".join(sorted_languages).upper()
    base_name = "_".join(sorted_languages)
    
    prompty_file = f"MULTILINGUAL/{folder_name}/chat_query_rewrite_{base_name}.prompty"
    tools_file = f"MULTILINGUAL/{folder_name}/chat_query_rewrite_tools_{base_name}.json"
    
    return prompty_file, tools_file


def get_monolingual_prompt_files(content_language: str) -> tuple[str, str]:
    """
    Get the monolingual prompt file paths.
    Returns (prompty_file, tools_file) relative paths.
    """
    lang_upper = content_language.upper()
    lang_lower = content_language.lower()
    
    prompty_file = f"MONOLINGUAL/{lang_upper}/chat_query_rewrite_{lang_lower}.prompty"
    tools_file = f"MONOLINGUAL/{lang_upper}/chat_query_rewrite_tools_{lang_lower}.json"
    
    return prompty_file, tools_file
