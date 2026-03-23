"""
Anthropic Claude Client Implementation

Implements the LLM client interface for Anthropic's Claude API.
Supports Claude 3.5 Sonnet, Claude 3.5 Haiku, and Claude 3 Opus.
Implements prompt caching for cost optimization.

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
    - Automatic retry on rate limits
    - Role-based system prompts
    
    Example:
        >>> config = LLMConfig(api_key="sk-...", model="claude-3-5-sonnet-20241022")
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
        """
        super().__init__(config)
        
        # Get API key from config or environment
        api_key = config.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "Anthropic API key required. Set ANTHROPIC_API_KEY environment "
                "variable or pass api_key in config."
            )
        
        # Try to import Anthropic SDK
        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            raise ImportError(
                "anthropic package not installed. "
                "Install with: pip install anthropic>=0.40.0"
            )
        
        # Initialize Anthropic client
        self.client = AsyncAnthropic(
            api_key=api_key,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries
        )
        
        logger.info(f"Initialized Anthropic client with model: {config.model}")
    
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
        - Automatic retry on rate limits
        
        Args:
            messages: Conversation history
            tools: Available tools for tool use
            system_prompt: System prompt override
            **kwargs: Additional parameters (max_tokens, temperature, etc.)
            
        Returns:
            LLMResponse with content and optional tool uses
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
            
            # Parse response
            content_text = ""
            tool_uses = []
            
            for block in response.content:
                if hasattr(block, 'type'):
                    if block.type == "text":
                        content_text += block.text
                    elif block.type == "tool_use":
                        tool_uses.append(ToolUse(
                            id=block.id,
                            name=block.name,
                            input=dict(block.input) if block.input else {}
                        ))
            
            # Build usage stats
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            }
            
            # Add cache stats if available
            if hasattr(response.usage, 'cache_read_input_tokens'):
                usage["cache_read_tokens"] = response.usage.cache_read_input_tokens
                if response.usage.cache_read_input_tokens > 0:
                    logger.info(
                        f"Cache efficiency: {response.usage.cache_read_input_tokens} "
                        f"tokens read from cache"
                    )
            
            # Update usage stats
            self._update_usage(usage)
            
            return LLMResponse(
                content=content_text,
                tool_uses=tool_uses,
                stop_reason=response.stop_reason,
                usage=usage,
                model=response.model
            )
            
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise
    
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
        
        final_message = None
        
        try:
            async with self.client.messages.stream(**request_params) as stream:
                async for text in stream.text_stream:
                    yield text
                final_message = await stream.get_final_message()
        except Exception as e:
            logger.error(f"Anthropic streaming error: {e}")
            raise
        
        # Update usage after streaming completes
        if final_message:
            self._update_usage({
                "total_tokens": (
                    final_message.usage.input_tokens + 
                    final_message.usage.output_tokens
                ),
                "input_tokens": final_message.usage.input_tokens,
                "output_tokens": final_message.usage.output_tokens,
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
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in tools
        ]
    
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
