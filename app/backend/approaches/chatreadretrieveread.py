from collections.abc import Awaitable
from typing import Any, Optional, Union, cast
import re
import logging
import os

from azure.search.documents.agent.aio import KnowledgeAgentRetrievalClient
from azure.search.documents.aio import SearchClient
from azure.search.documents.models import VectorQuery
from openai import AsyncOpenAI, AsyncStream
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
)

from approaches.approach import DataPoints, ExtraInfo, ThoughtStep, Document
from approaches.chatapproach import ChatApproach
from approaches.promptmanager import PromptManager
from core.authentication import AuthenticationHelper
from core.multilingual_helper import (
    get_multilingual_prompt_files, 
    get_monolingual_prompt_files,
    get_supported_languages
)

logger = logging.getLogger(__name__)

class ChatReadRetrieveReadApproach(ChatApproach):
    """
    A multi-step approach that first uses OpenAI to turn the user's question into a search query,
    then uses Azure AI Search to retrieve relevant documents, and then sends the conversation history,
    original user question, and search results to OpenAI to generate a response.
    """

    def __init__(
        self,
        *,
        search_client: SearchClient,
        search_index_name: str,
        agent_model: Optional[str],
        agent_deployment: Optional[str],
        agent_client: KnowledgeAgentRetrievalClient,
        auth_helper: AuthenticationHelper,
        openai_client: AsyncOpenAI,
        chatgpt_model: str,
        chatgpt_deployment: Optional[str],  # Not needed for non-Azure OpenAI
        embedding_deployment: Optional[str],  # Not needed for non-Azure OpenAI or for retrieval_mode="text"
        embedding_model: str,
        embedding_dimensions: int,
        embedding_field: str,
        sourcepage_field: str,
        content_field: str,
        query_language: str,
        query_speller: str,
        prompt_manager: PromptManager,
        reasoning_effort: Optional[str] = None,
    ):
        super().__init__(
            search_client,
            openai_client,
            auth_helper,
            query_language,
            query_speller,
            embedding_deployment,
            embedding_model,
            embedding_dimensions,
            embedding_field,
            openai_host="azure",
            vision_endpoint="",
            vision_token_provider=lambda: None,
            prompt_manager=prompt_manager,
            reasoning_effort=reasoning_effort,
        )
        self.search_index_name = search_index_name
        self.agent_model = agent_model
        self.agent_deployment = agent_deployment
        self.agent_client = agent_client
        self.chatgpt_model = chatgpt_model
        self.chatgpt_deployment = chatgpt_deployment
        self.sourcepage_field = sourcepage_field
        self.content_field = content_field
        
        # Initialize search mode based on environment variables
        self.enable_multilingual_search = os.getenv("ENABLE_MULTILINGUAL_SEARCH", "false").lower() == "true"
        self.content_language = os.getenv("CONTENT_LANGUAGE")
        
        # These will be set based on search mode
        self.query_rewrite_prompt = None
        self.query_rewrite_tools = None
        self.answer_prompt = self.prompt_manager.load_prompt("chat_answer_question.prompty")
        
        # Load appropriate prompt files based on configuration
        self._load_search_prompts()

    def _load_search_prompts(self):
        """Load the appropriate prompt files based on search mode configuration"""
        try:
            if self.enable_multilingual_search:
                # Load multilingual prompts
                prompty_file, tools_file = get_multilingual_prompt_files()
                self.query_rewrite_prompt = self.prompt_manager.load_prompt(prompty_file)
                self.query_rewrite_tools = self.prompt_manager.load_tools(tools_file)
                logger.info(f"Loaded multilingual prompts: {prompty_file}, {tools_file}")
            else:
                # Load monolingual prompts
                if not self.content_language:
                    raise ValueError("CONTENT_LANGUAGE is required for monolingual mode")
                
                prompty_file, tools_file = get_monolingual_prompt_files(self.content_language)
                self.query_rewrite_prompt = self.prompt_manager.load_prompt(prompty_file)
                self.query_rewrite_tools = self.prompt_manager.load_tools(tools_file)
                logger.info(f"Loaded monolingual prompts for {self.content_language}: {prompty_file}, {tools_file}")
                
        except Exception as e:
            logger.error(f"Failed to load search prompts: {e}")
            raise ValueError(f"Failed to load search prompts: {e}")
    
    def _clean_and_escape_query(self, query_text: str) -> str:
        """
        Clean and escape the search query for Lucene Simple Query Parser
        """
        # Full text search uses Lucene Simple Query Parser https://lucene.apache.org/core/6_6_1/queryparser/org/apache/lucene/queryparser/simple/SimpleQueryParser.html
        # The current implementation uses '|' to delimit different phrasings or languages in the search query. For simplicity, we delete those, as they have no meaning.
        try:
            query_text = query_text.replace("|", "")
            special_chars = r'+|"()\'\\'
            pattern = re.compile(f'([{re.escape(special_chars)}])')
            return pattern.sub(r'\\\1', query_text)
        except Exception as e:
            logger.warning(f"Exception encountered : {e}. Returning original query text {query_text}")
            return query_text

    async def run_until_final_call(
        self,
        messages: list[ChatCompletionMessageParam],
        overrides: dict[str, Any],
        auth_claims: dict[str, Any],
        should_stream: bool = False,
    ) -> tuple[ExtraInfo, Union[Awaitable[ChatCompletion], Awaitable[AsyncStream[ChatCompletionChunk]]]]:
        use_agentic_retrieval = True if overrides.get("use_agentic_retrieval") else False
        original_user_query = messages[-1]["content"]

        reasoning_model_support = self.GPT_REASONING_MODELS.get(self.chatgpt_model)
        if reasoning_model_support and (not reasoning_model_support.streaming and should_stream):
            raise Exception(
                f"{self.chatgpt_model} does not support streaming. Please use a different model or disable streaming."
            )
        if use_agentic_retrieval:
            extra_info = await self.run_agentic_retrieval_approach(messages, overrides, auth_claims)
        else:
            extra_info = await self.run_search_approach(messages, overrides, auth_claims)

        messages = self.prompt_manager.render_prompt(
            self.answer_prompt,
            self.get_system_prompt_variables(overrides.get("prompt_template"))
            | {
                "include_follow_up_questions": bool(overrides.get("suggest_followup_questions")),
                "past_messages": messages[:-1],
                "user_query": original_user_query,
                "text_sources": extra_info.data_points.text,
            },
        )

        chat_coroutine = cast(
            Union[Awaitable[ChatCompletion], Awaitable[AsyncStream[ChatCompletionChunk]]],
            self.create_chat_completion(
                self.chatgpt_deployment,
                self.chatgpt_model,
                messages,
                overrides,
                self.get_response_token_limit(self.chatgpt_model, 1024),
                should_stream,
            ),
        )
        extra_info.thoughts.append(
            self.format_thought_step_for_chatcompletion(
                title="Prompt to generate answer",
                messages=messages,
                overrides=overrides,
                model=self.chatgpt_model,
                deployment=self.chatgpt_deployment,
                usage=None,
            )
        )
        return (extra_info, chat_coroutine)

    async def run_search_approach(
        self, messages: list[ChatCompletionMessageParam], overrides: dict[str, Any], auth_claims: dict[str, Any]
    ):
        use_text_search = overrides.get("retrieval_mode") in ["text", "hybrid", None]
        use_vector_search = overrides.get("retrieval_mode") in ["vectors", "hybrid", None]
        use_semantic_ranker = True if overrides.get("semantic_ranker") else False
        use_semantic_captions = True if overrides.get("semantic_captions") else False
        use_query_rewriting = True if overrides.get("query_rewriting") else False
        top = overrides.get("top", 3)
        minimum_search_score = overrides.get("minimum_search_score", 0.0)
        minimum_reranker_score = overrides.get("minimum_reranker_score", 0.0)
        search_index_filter = self.build_filter(overrides, auth_claims)

        original_user_query = messages[-1]["content"]
        if not isinstance(original_user_query, str):
            raise ValueError("The most recent message content must be a string.")

        query_messages = self.prompt_manager.render_prompt(
            self.query_rewrite_prompt, {"user_query": original_user_query, "past_messages": messages[:-1]}
        )
        tools: list[ChatCompletionToolParam] = self.query_rewrite_tools

        # STEP 1: Generate an optimized keyword search query based on the chat history and the last question

        chat_completion = cast(
            ChatCompletion,
            await self.create_chat_completion(
                self.chatgpt_deployment,
                self.chatgpt_model,
                messages=query_messages,
                overrides=overrides,
                response_token_limit=self.get_response_token_limit(
                    self.chatgpt_model, 1000 
                ), #need minimum 500 max_tokens to get three function calls
                temperature=0.0,  # Minimize creativity for search query generation 
                tools=tools,
                reasoning_effort="low",  # Minimize reasoning for search query generation, o-series models only
            ),
        )

        # STEP 2: Retrieve relevant documents from the search index with the GPT optimized query
        
        # Get search query from the chat completion
        query_text = self.get_search_query(chat_completion, original_user_query)
        query_text = self._clean_and_escape_query(query_text)
        
        # If retrieval mode includes vectors, compute an embedding for the query
        vectors: list[VectorQuery] = []
        if use_vector_search:
            vectors.append(await self.compute_text_embedding(query_text))
        
        # Perform search based on mode
        if self.enable_multilingual_search:
            # Use multilingual search approach
            multilingual_queries = self.get_multilingual_search_queries(chat_completion)
            
            if multilingual_queries:
                results = await self._perform_multilingual_search(
                    search_queries=multilingual_queries,
                    top_per_language=top,
                    filter_clause=search_index_filter,
                    vectors=vectors,
                    use_text_search=use_text_search,
                    use_vector_search=use_vector_search,
                    use_semantic_ranker=use_semantic_ranker,
                    use_semantic_captions=use_semantic_captions,
                    minimum_search_score=minimum_search_score,
                    minimum_reranker_score=minimum_reranker_score,
                    use_query_rewriting=use_query_rewriting,
                )
            else:
                # Fallback to traditional search if no multilingual queries found
                logger.warning("Multilingual mode enabled but no multilingual queries found, falling back to traditional search")
                results = await self.search(
                    top,
                    query_text,
                    search_index_filter,
                    vectors,
                    use_text_search,
                    use_vector_search,
                    use_semantic_ranker,
                    use_semantic_captions,
                    minimum_search_score,
                    minimum_reranker_score,
                    use_query_rewriting,
                )
        else:
            # Use monolingual search approach with single content field
            results = await self.search(
                top,
                query_text,
                search_index_filter,
                vectors,
                use_text_search,
                use_vector_search,
                use_semantic_ranker,
                use_semantic_captions,
                minimum_search_score,
                minimum_reranker_score,
                use_query_rewriting,
            )

        # STEP 3: Generate a contextual and content specific answer using the search results and chat history
        text_sources = self.get_sources_content(results, use_semantic_captions, use_image_citation=False)

        extra_info = ExtraInfo(
            DataPoints(text=text_sources),
            thoughts=[
                self.format_thought_step_for_chatcompletion(
                    title="Prompt to generate search query",
                    messages=query_messages,
                    overrides=overrides,
                    model=self.chatgpt_model,
                    deployment=self.chatgpt_deployment,
                    usage=chat_completion.usage,
                    reasoning_effort="low",
                ),
                ThoughtStep(
                    "Search using generated search query",
                    query_text,
                    {
                        "use_semantic_captions": use_semantic_captions,
                        "use_semantic_ranker": use_semantic_ranker,
                        "use_query_rewriting": use_query_rewriting,
                        "top": top,
                        "filter": search_index_filter,
                        "use_vector_search": use_vector_search,
                        "use_text_search": use_text_search,
                    },
                ),
                ThoughtStep(
                    "Search results",
                    [result.serialize_for_results() for result in results],
                ),
            ],
        )
        return extra_info

    async def run_agentic_retrieval_approach(
        self,
        messages: list[ChatCompletionMessageParam],
        overrides: dict[str, Any],
        auth_claims: dict[str, Any],
    ):
        minimum_reranker_score = overrides.get("minimum_reranker_score", 0)
        search_index_filter = self.build_filter(overrides, auth_claims)
        top = overrides.get("top", 3)
        max_subqueries = overrides.get("max_subqueries", 10)
        results_merge_strategy = overrides.get("results_merge_strategy", "interleaved")
        # 50 is the amount of documents that the reranker can process per query
        max_docs_for_reranker = max_subqueries * 50

        response, results = await self.run_agentic_retrieval(
            messages=messages,
            agent_client=self.agent_client,
            search_index_name=self.search_index_name,
            top=top,
            filter_add_on=search_index_filter,
            minimum_reranker_score=minimum_reranker_score,
            max_docs_for_reranker=max_docs_for_reranker,
            results_merge_strategy=results_merge_strategy,
        )

        text_sources = self.get_sources_content(results, use_semantic_captions=False, use_image_citation=False)

        extra_info = ExtraInfo(
            DataPoints(text=text_sources),
            thoughts=[
                ThoughtStep(
                    "Use agentic retrieval",
                    messages,
                    {
                        "reranker_threshold": minimum_reranker_score,
                        "max_docs_for_reranker": max_docs_for_reranker,
                        "results_merge_strategy": results_merge_strategy,
                        "filter": search_index_filter,
                    },
                ),
                ThoughtStep(
                    f"Agentic retrieval results (top {top})",
                    [result.serialize_for_results() for result in results],
                    {
                        "query_plan": (
                            [activity.as_dict() for activity in response.activity] if response.activity else None
                        ),
                        "model": self.agent_model,
                        "deployment": self.agent_deployment,
                    },
                ),
            ],
        )
        return extra_info

    async def _perform_multilingual_search(
        self,
        search_queries: dict[str, str],
        top_per_language: int,
        filter_clause: Optional[str],
        vectors: list[VectorQuery],
        use_text_search: bool,
        use_vector_search: bool,
        use_semantic_ranker: bool,
        use_semantic_captions: bool,
        minimum_search_score: Optional[float] = None,
        minimum_reranker_score: Optional[float] = None,
        use_query_rewriting: Optional[bool] = None,
    ):
        """
        Perform multilingual search across multiple languages and merge results.
        This implementation reuses the existing self.search() method for each language.
        """
        import asyncio
        
        all_results = []
        search_tasks = []
        
        # Create search tasks for each language
        for lang_code, query_text in search_queries.items():
            # Create language-specific filter
            lang_filter = f"language eq '{lang_code}'"
            combined_filter = self._combine_filters(filter_clause, lang_filter)
            
            # Create language-specific vectors with search fields
            lang_vectors = []
            if use_vector_search and vectors:
                for vector in vectors:
                    # Create a copy of the vector with language-specific search fields
                    lang_vector = VectorQuery(
                        vector=vector.vector,
                        k_nearest_neighbors=vector.k_nearest_neighbors,
                        fields=vector.fields,  # Keep existing vector fields
                        exhaustive=vector.exhaustive,
                        oversampling=vector.oversampling,
                        threshold=vector.threshold
                    )
                    lang_vectors.append(lang_vector)
            
            # Configure search fields for language-specific content
            search_fields = [f"content_{lang_code}"] if use_text_search else None
            
            # Create a task that uses the existing search method
            task = self.search(
                top=top_per_language,
                query_text=query_text,
                filter=combined_filter,
                vectors=lang_vectors,
                use_text_search=use_text_search,
                use_vector_search=use_vector_search,
                use_semantic_ranker=use_semantic_ranker,
                use_semantic_captions=use_semantic_captions,
                minimum_search_score=minimum_search_score,
                minimum_reranker_score=minimum_reranker_score,
                use_query_rewriting=use_query_rewriting,
                search_fields=search_fields,
            )
            search_tasks.append(task)
        
        # Execute all searches in parallel
        if search_tasks:
            language_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            
            # Combine results from all languages
            for i, result in enumerate(language_results):
                if isinstance(result, Exception):
                    logger.error(f"Error in language search {i}: {result}")
                    continue
                all_results.extend(result)
        
        # Rerank and return top results
        return self._rerank_multilingual_results(all_results, top_per_language)

    def _combine_filters(self, base_filter: Optional[str], additional_filter: str) -> str:
        """Combine multiple filter clauses"""
        if not base_filter:
            return additional_filter
        return f"({base_filter}) and ({additional_filter})"
    
    def _rerank_multilingual_results(self, all_results, final_top: int):
        """Rerank results from all languages based on their scores"""
        if not all_results:
            return []
        
        # Sort by reranker score first (if available), then by search score
        def sort_key(doc):
            reranker_score = doc.reranker_score if doc.reranker_score is not None else 0.0
            search_score = doc.score if doc.score is not None else 0.0
            return (reranker_score, search_score)
        
        sorted_results = sorted(all_results, key=sort_key, reverse=True)
        
        # Return top results
        return sorted_results[:final_top]

    def get_multilingual_search_queries(self, chat_completion: ChatCompletion) -> dict[str, str]:
        """Parse multilingual search queries from LLM tool responses"""
        queries = {}
        
        if not chat_completion.choices or not chat_completion.choices[0].message.tool_calls:
            return queries
        
        for tool_call in chat_completion.choices[0].message.tool_calls:
            function_name = tool_call.function.name
            if not function_name.startswith("search_sources_"):
                continue
            
            # Extract language code from function name (e.g., search_sources_DE -> de)
            lang_code = function_name.split("_")[-1].lower()
            
            # Get the search query from arguments
            try:
                import json
                arguments = json.loads(tool_call.function.arguments) if isinstance(tool_call.function.arguments, str) else tool_call.function.arguments
                search_query = arguments.get("search_query", "")
                if search_query:
                    # Clean up the query (remove pipe separators used in current implementation)
                    cleaned_query = search_query.replace("|", " ").strip()
                    queries[lang_code] = cleaned_query
            except Exception as e:
                logger.warning(f"Failed to parse tool call arguments: {e}")
                continue
        
        return queries
