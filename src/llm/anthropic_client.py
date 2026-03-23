"""
Anthropic Claude Client Implementation

Implements the LLM client interface for Anthropic's Claude API.
Supports Claude 3.5 Sonnet, Claude 3.5 Haiku, and Claude 3 Opus.
Implements prompt caching for cost optimization.

Phase 3 Enhancements:
- Enhanced error handling with custom exceptions
- Exponential backoff retry logic
- Improved response parsing
- Better error recovery

As specified in Section 1.3 of the Phase 2 LLM/MCP Integration Specification.
"""

from typing import AsyncIterator, List, Optional, Dict, Any
import logging
import asyncio
import os

from .base_client import (
    BaseLLMClient,
    ChatMessage,
    MessageRole,
    ToolDefinition,
    ToolUse,
    LLMResponse,
    LLMConfig,
)
from .exceptions import (
    LLMError,
    LLMConfigurationError,
    LLMAuthenticationError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMContextLengthError,
    LLMResponseError,
    LLMToolUseError,
    LLMServiceUnavailableError,
    get_exception_for_status,
)
from .retry import RetryHandler, RetryConfig
from .response_parser import ResponseParser, StreamingResponseParser

logger = logging.getLogger(__name__)


class AnthropicClient(BaseLLMClient):
    """
    Anthropic Claude API client implementation.
    
    Supports Claude 3.5 Sonnet, Claude 3.5 Haiku, and Claude 3 Opus.
    Implements prompt caching for cost optimization.
    
    Features:
    - Streaming and non-streaming completions
    - Tool use support
    - Prompt caching for cost optimization
    - Automatic retry with exponential backoff
    - Comprehensive error handling
    - Role-based system prompts
    
    Example:
        >>> config = LLMConfig(api_key="sk-ant-...", model="claude-3-5-sonnet-20241022")
        >>> client = AnthropicClient(config)
        >>> response = await client.complete([
        ...     ChatMessage(role=MessageRole.USER, content="Hello!")
        ... ])
        >>> print(response.content)
    """
    
    # Default system prompts for each agent role
    SYSTEM_PROMPTS = {
        "manager": """You are the Manager Agent in AutoDev, an autonomous software development system.

Your responsibilities:
- Decompose complex tasks into atomic subtasks
- Assign tasks to specialized workers (Coder, Reviewer, Tester)
- Monitor execution progress and handle failures
- Resolve conflicts between parallel workers
- Synthesize final results

You must:
- Think through task dependencies carefully
- Provide clear, unambiguous task specifications
- Make decisions based on quality gates and acceptance criteria
- Communicate status updates clearly

Available worker types:
- Coder: Implements features, fixes bugs, refactors code
- Reviewer: Reviews code quality, validates acceptance criteria
- Tester: Generates and executes tests

Output structured task assignments with clear specifications.""",
        
        "coder": """You are the Coder Agent in AutoDev, specialized in code generation and modification.

Your capabilities:
- Implement features from specifications
- Fix bugs based on reports
- Refactor code for quality improvements
- Write documentation

You must:
- Follow existing code style and patterns
- Maintain backward compatibility when required
- Write clean, self-documenting code
- Include appropriate error handling
- Consider edge cases

Output:
1. Clear description of changes made
2. Rationale for implementation choices
3. Any assumptions or edge cases handled""",
        
        "reviewer": """You are the Reviewer Agent in AutoDev, responsible for quality assurance.

Your responsibilities:
- Review code changes for correctness
- Check coding standards compliance
- Identify security vulnerabilities
- Validate acceptance criteria
- Detect anti-patterns

Review checklist:
1. Correctness: Does code do what it should?
2. Quality: Is it readable and maintainable?
3. Security: Are there vulnerabilities?
4. Testing: Is coverage adequate?
5. Performance: Are there obvious issues?

Provide:
- Clear verdict: approved, needs_changes, or rejected
- Specific findings with severity levels
- Actionable recommendations""",
        
        "tester": """You are the Tester Agent in AutoDev, specialized in test generation and execution.

Your responsibilities:
- Generate comprehensive test suites
- Execute tests and analyze results
- Ensure adequate code coverage
- Identify test gaps

You must:
- Write unit tests, integration tests, and edge case tests
- Use appropriate testing frameworks
- Provide clear test results
- Suggest improvements for test coverage

Output test files and execution results.""",
    }
    
    def __init__(self, config: LLMConfig):
        """
        Initialize Anthropic client.
        
        Args:
            config: LLM configuration including API key
            
        Raises:
            LLMConfigurationError: If configuration is invalid
            LLMAuthenticationError: If API key is missing
        """
        super().__init__(config)
        
        # Validate configuration
        self._validate_config(config)
        
        # Get API key from config or environment
        api_key = config.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMAuthenticationError(
                "Anthropic API key required. Set ANTHROPIC_API_KEY environment "
                "variable or pass api_key in config.",
                provider="anthropic"
            )
        
        # Try to import Anthropic SDK
        try:
            from anthropic import AsyncAnthropic, APIStatusError, RateLimitError
            self._APIStatusError = APIStatusError
            self._RateLimitError = RateLimitError
        except ImportError:
            raise LLMConfigurationError(
                "anthropic package not installed. "
                "Install with: pip install anthropic>=0.40.0",
                provider="anthropic"
            )
        
        # Initialize Anthropic client
        self.client = AsyncAnthropic(
            api_key=api_key,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            max_retries=0  # We handle retries ourselves
        )
        
        # Initialize retry handler
        retry_config = RetryConfig(
            max_retries=config.max_retries,
            base_delay=config.retry_backoff_seconds,
            max_delay=60.0,
            exponential_base=2.0,
            jitter=True,
        )
        self._retry_handler = RetryHandler(retry_config)
        
        # Initialize response parser
        self._parser = ResponseParser()
        
        logger.info(f"Initialized Anthropic client with model: {config.model}")
    
    def _validate_config(self, config: LLMConfig) -> None:
        """
        Validate LLM configuration.
        
        Args:
            config: Configuration to validate
            
        Raises:
            LLMConfigurationError: If configuration is invalid
        """
        if config.max_tokens < 1:
            raise LLMConfigurationError(
                "max_tokens must be at least 1",
                config_key="max_tokens"
            )
        
        if config.max_tokens > 200000:
            raise LLMConfigurationError(
                "max_tokens exceeds maximum (200000)",
                config_key="max_tokens"
            )
        
        if not 0 <= config.temperature <= 2:
            raise LLMConfigurationError(
                "temperature must be between 0 and 2",
                config_key="temperature"
            )
        
        if config.max_retries < 0:
            raise LLMConfigurationError(
                "max_retries cannot be negative",
                config_key="max_retries"
            )
    
    async def complete(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Complete conversation using Claude API.
        
        Features:
        - Prompt caching for system messages
        - Tool use support
        - Automatic retry with exponential backoff
        - Comprehensive error handling
        
        Args:
            messages: Conversation history
            tools: Available tools for tool use
            system_prompt: System prompt override
            **kwargs: Additional parameters (max_tokens, temperature, etc.)
            
        Returns:
            LLMResponse with content and optional tool uses
            
        Raises:
            LLMError: On API errors (with specific subclasses)
        """
        # Use retry handler for the API call
        return await self._retry_handler.execute_with_retry(
            self._complete_impl,
            messages,
            tools=tools,
            system_prompt=system_prompt,
            **kwargs
        )
    
    async def _complete_impl(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Internal implementation of complete (without retry logic).
        """
        # Convert messages to Anthropic format
        anthropic_messages = self._convert_messages(messages)
        
        # Build request parameters
        request_params = {
            "model": kwargs.get("model", self.config.model),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": anthropic_messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
        }
        
        # Add system prompt with caching
        if system_prompt:
            if self.config.enable_caching:
                request_params["system"] = [
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"}
                    }
                ]
            else:
                request_params["system"] = system_prompt
        
        # Add tools if provided
        if tools:
            request_params["tools"] = self._convert_tools(tools)
        
        try:
            # Make API call
            logger.debug(f"Making Anthropic API call with {len(messages)} messages")
            response = await self.client.messages.create(**request_params)
            
            # Parse response using our parser
            llm_response = self._parser.parse_anthropic_response(response)
            
            # Log cache efficiency
            usage = llm_response.usage
            if usage.get("cache_read_tokens", 0) > 0:
                logger.info(
                    f"Cache efficiency: {usage['cache_read_tokens']} "
                    f"tokens read from cache"
                )
            
            # Update usage stats
            self._update_usage(usage)
            
            # Validate response
            is_valid, issues = self._parser.validate_response(llm_response)
            if not is_valid:
                for issue in issues:
                    logger.warning(f"Response validation: {issue}")
            
            return llm_response
            
        except self._RateLimitError as e:
            # Handle rate limit specifically
            retry_after = None
            if hasattr(e, 'response') and hasattr(e.response, 'headers'):
                retry_after_str = e.response.headers.get('retry-after')
                if retry_after_str:
                    try:
                        retry_after = float(retry_after_str)
                    except ValueError:
                        pass
            
            raise LLMRateLimitError(
                f"Rate limit exceeded: {e}",
                retry_after=retry_after,
                provider="anthropic",
                model=self.config.model,
                details={'status_code': getattr(e, 'status_code', 429)}
            )
            
        except self._APIStatusError as e:
            # Map status codes to specific exceptions
            status_code = getattr(e, 'status_code', 500)
            message = str(e)
            
            # Check for specific error types based on message
            if 'context_length' in message.lower() or 'too long' in message.lower():
                raise LLMContextLengthError(
                    message,
                    provider="anthropic",
                    model=self.config.model,
                    details={'status_code': status_code}
                )
            
            raise get_exception_for_status(
                status_code,
                message,
                provider="anthropic",
                model=self.config.model,
                details={'status_code': status_code}
            )
            
        except asyncio.TimeoutError:
            raise LLMTimeoutError(
                f"Request timed out after {self.config.timeout_seconds}s",
                timeout_seconds=self.config.timeout_seconds,
                provider="anthropic",
                model=self.config.model
            )
            
        except Exception as e:
            logger.error(f"Unexpected Anthropic API error: {e}")
            raise LLMError(
                f"Unexpected error: {e}",
                provider="anthropic",
                model=self.config.model
            )
    
    async def stream_complete(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Stream completion from Claude.
        
        Args:
            messages: Conversation history
            tools: Available tools for tool use
            system_prompt: System prompt override
            **kwargs: Additional parameters
            
        Yields:
            Text chunks as they arrive
            
        Raises:
            LLMError: On API errors
        """
        anthropic_messages = self._convert_messages(messages)
        
        request_params = {
            "model": kwargs.get("model", self.config.model),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": anthropic_messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
        }
        
        if system_prompt:
            request_params["system"] = system_prompt
        
        if tools:
            request_params["tools"] = self._convert_tools(tools)
        
        # Initialize streaming parser
        stream_parser = StreamingResponseParser()
        final_message = None
        stop_reason = "end_turn"
        model = self.config.model
        
        try:
            async with self.client.messages.stream(**request_params) as stream:
                async for event in stream:
                    text = stream_parser.process_event(event)
                    if text:
                        yield text
                
                # Get final message for usage stats
                final_message = await stream.get_final_message()
                stop_reason = getattr(final_message, 'stop_reason', 'end_turn')
                model = getattr(final_message, 'model', self.config.model)
                
        except self._RateLimitError as e:
            raise LLMRateLimitError(
                f"Rate limit exceeded during streaming: {e}",
                provider="anthropic",
                model=self.config.model
            )
        except self._APIStatusError as e:
            raise get_exception_for_status(
                getattr(e, 'status_code', 500),
                str(e),
                provider="anthropic",
                model=self.config.model
            )
        except Exception as e:
            logger.error(f"Anthropic streaming error: {e}")
            raise LLMError(
                f"Streaming error: {e}",
                provider="anthropic",
                model=self.config.model
            )
        
        # Update usage after streaming completes
        if final_message and hasattr(final_message, 'usage'):
            usage_obj = final_message.usage
            self._update_usage({
                "total_tokens": usage_obj.input_tokens + usage_obj.output_tokens,
                "input_tokens": usage_obj.input_tokens,
                "output_tokens": usage_obj.output_tokens,
            })
    
    def _convert_messages(self, messages: List[ChatMessage]) -> List[Dict[str, Any]]:
        """
        Convert ChatMessage list to Anthropic format.
        
        Args:
            messages: List of ChatMessage objects
            
        Returns:
            List of message dictionaries in Anthropic format
        """
        anthropic_messages = []
        
        for msg in messages:
            # Skip system messages (handled separately in Anthropic API)
            if msg.role == MessageRole.SYSTEM:
                continue
            
            # Build content based on metadata
            if msg.metadata and "tool_uses" in msg.metadata:
                # Message with tool use blocks
                content = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tool_use in msg.metadata["tool_uses"]:
                    content.append({
                        "type": "tool_use",
                        "id": tool_use.get("id", ""),
                        "name": tool_use.get("name", ""),
                        "input": tool_use.get("input", {}),
                    })
            elif msg.metadata and "tool_result" in msg.metadata:
                # Tool result message
                content = [{
                    "type": "tool_result",
                    "tool_use_id": msg.metadata.get("tool_use_id", ""),
                    "content": msg.content,
                    "is_error": msg.metadata.get("is_error", False),
                }]
            else:
                # Regular text message
                content = msg.content
            
            anthropic_msg = {
                "role": msg.role.value,
                "content": content,
            }
            
            anthropic_messages.append(anthropic_msg)
        
        return anthropic_messages
    
    def _convert_tools(self, tools: List[ToolDefinition]) -> List[Dict[str, Any]]:
        """
        Convert ToolDefinition to Anthropic format.
        
        Args:
            tools: List of ToolDefinition objects
            
        Returns:
            List of tool dictionaries in Anthropic format
        """
        converted_tools = []
        for tool in tools:
            converted = {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            # Add caching for tools if enabled
            if self.config.enable_caching:
                converted["cache_control"] = {"type": "ephemeral"}
            converted_tools.append(converted)
        
        return converted_tools
    
    @classmethod
    def get_system_prompt(cls, role: str) -> str:
        """
        Get system prompt for a given agent role.
        
        Args:
            role: Agent role (manager, coder, reviewer, tester)
            
        Returns:
            System prompt string
        """
        return cls.SYSTEM_PROMPTS.get(role, "")
    
    def create_tool_result_message(
        self,
        tool_use_id: str,
        content: str,
        is_error: bool = False
    ) -> ChatMessage:
        """
        Create a tool result message for conversation history.
        
        Args:
            tool_use_id: ID of the tool use being responded to
            content: Result content
            is_error: Whether this is an error result
            
        Returns:
            ChatMessage with tool result
        """
        return ChatMessage(
            role=MessageRole.USER,
            content=content,
            metadata={
                "tool_result": True,
                "tool_use_id": tool_use_id,
                "is_error": is_error,
            }
        )
    
    def get_retry_stats(self) -> Dict[str, Any]:
        """
        Get retry statistics.
        
        Returns:
            Dictionary with retry statistics
        """
        return self._retry_handler.get_stats()
    
    def reset_retry_stats(self) -> None:
        """Reset retry statistics."""
        self._retry_handler.reset_stats()


# Alias for backward compatibility and clarity
AnthropicLLMClient = AnthropicClient


__all__ = [
    "AnthropicClient",
    "AnthropicLLMClient",
]
