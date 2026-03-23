"""
AutoDev LLM Client - Main Interface

Provides a unified interface for LLM interactions with provider abstraction.
This is the primary entry point for using LLM functionality in AutoDev.

Phase 2 Implementation:
- Provider abstraction with factory pattern
- Anthropic Claude provider implementation
- Streaming and non-streaming completions
- Tool use support
- Usage tracking and cost optimization

Usage:
    from llm.client import LLMClient, LLMConfig
    
    config = LLMConfig(api_key="sk-ant-...", model="claude-3-5-sonnet-20241022")
    client = LLMClient(config)
    
    response = await client.complete("Hello, world!")
    print(response.content)
"""

from typing import AsyncIterator, Dict, List, Optional, Any, Union
import logging
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
from .anthropic_client import AnthropicClient

logger = logging.getLogger(__name__)


# Provider registry for factory pattern
_PROVIDER_REGISTRY: Dict[str, type] = {
    "anthropic": AnthropicClient,
}


def register_provider(name: str, client_class: type) -> None:
    """
    Register a new LLM provider.
    
    Args:
        name: Provider name (e.g., "openai", "anthropic")
        client_class: Client class that inherits from BaseLLMClient
    """
    _PROVIDER_REGISTRY[name.lower()] = client_class
    logger.info(f"Registered LLM provider: {name}")


def get_available_providers() -> List[str]:
    """
    Get list of available LLM providers.
    
    Returns:
        List of provider names
    """
    return list(_PROVIDER_REGISTRY.keys())


def create_client(config: LLMConfig) -> BaseLLMClient:
    """
    Factory function to create an LLM client based on configuration.
    
    Args:
        config: LLM configuration specifying provider and settings
        
    Returns:
        Appropriate LLM client instance
        
    Raises:
        ValueError: If provider is not supported
        
    Example:
        >>> config = LLMConfig(provider="anthropic", api_key="sk-ant-...")
        >>> client = create_client(config)
        >>> isinstance(client, AnthropicClient)
        True
    """
    provider = config.provider.lower()
    
    if provider not in _PROVIDER_REGISTRY:
        available = ", ".join(get_available_providers())
        raise ValueError(
            f"Unsupported LLM provider: {provider}. "
            f"Available providers: {available}"
        )
    
    client_class = _PROVIDER_REGISTRY[provider]
    return client_class(config)


class LLMClient:
    """
    High-level LLM client with unified interface.
    
    Wraps provider-specific implementations and provides a simple API
    for common LLM operations.
    
    Features:
    - Automatic provider selection based on configuration
    - Both async and convenience methods
    - Conversation history management
    - Usage tracking
    - Streaming support
    - Tool/function calling
    
    Example:
        >>> config = LLMConfig(api_key="sk-ant-...")
        >>> client = LLMClient(config)
        >>> 
        >>> # Simple completion
        >>> response = await client.complete("What is 2+2?")
        >>> print(response.content)
        "4"
        >>> 
        >>> # With conversation history
        >>> client.add_message(MessageRole.USER, "Hello!")
        >>> response = await client.complete()
        
        >>> # Streaming
        >>> async for chunk in client.stream("Tell me a story"):
        ...     print(chunk, end="")
    """
    
    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize LLM client.
        
        Args:
            config: Full LLM configuration (optional)
            provider: Provider name override (optional)
            api_key: API key override (optional)
            model: Model name override (optional)
            **kwargs: Additional configuration options
            
        Either config or at least api_key should be provided.
        """
        # Build config from parameters
        if config is None:
            config = LLMConfig()
        
        # Apply overrides
        if provider:
            config.provider = provider
        if api_key:
            config.api_key = api_key
        if model:
            config.model = model
        
        # Apply additional kwargs to config
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
            else:
                config.metadata[key] = value
        
        self.config = config
        self._client = create_client(config)
        self._conversation_history: List[ChatMessage] = []
    
    @property
    def provider(self) -> str:
        """Get the provider name."""
        return self.config.provider
    
    @property
    def model(self) -> str:
        """Get the current model name."""
        return self.config.model
    
    async def complete(
        self,
        prompt: Optional[str] = None,
        messages: Optional[List[ChatMessage]] = None,
        system_prompt: Optional[str] = None,
        tools: Optional[List[ToolDefinition]] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Complete a conversation with the LLM.
        
        Args:
            prompt: Simple text prompt (alternative to messages)
            messages: Full conversation history (alternative to prompt)
            system_prompt: System prompt override
            tools: Available tools for tool calling
            **kwargs: Additional provider-specific parameters
            
        Returns:
            LLMResponse with content and optional tool uses
            
        Example:
            >>> response = await client.complete("What is Python?")
            >>> print(response.content)
        """
        # Build message list
        if messages is not None:
            msg_list = list(messages)
        elif prompt is not None:
            msg_list = list(self._conversation_history)
            msg_list.append(ChatMessage(role=MessageRole.USER, content=prompt))
        else:
            msg_list = list(self._conversation_history)
        
        # Call underlying client
        response = await self._client.complete(
            messages=msg_list,
            tools=tools,
            system_prompt=system_prompt,
            **kwargs
        )
        
        return response
    
    async def stream(
        self,
        prompt: Optional[str] = None,
        messages: Optional[List[ChatMessage]] = None,
        system_prompt: Optional[str] = None,
        tools: Optional[List[ToolDefinition]] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Stream completion response.
        
        Args:
            prompt: Simple text prompt (alternative to messages)
            messages: Full conversation history (alternative to prompt)
            system_prompt: System prompt override
            tools: Available tools for tool calling
            **kwargs: Additional provider-specific parameters
            
        Yields:
            Text chunks as they arrive
            
        Example:
            >>> async for chunk in client.stream("Tell me a story"):
            ...     print(chunk, end="", flush=True)
        """
        # Build message list
        if messages is not None:
            msg_list = list(messages)
        elif prompt is not None:
            msg_list = list(self._conversation_history)
            msg_list.append(ChatMessage(role=MessageRole.USER, content=prompt))
        else:
            msg_list = list(self._conversation_history)
        
        # Stream from underlying client
        async for chunk in self._client.stream_complete(
            messages=msg_list,
            tools=tools,
            system_prompt=system_prompt,
            **kwargs
        ):
            yield chunk
    
    def add_message(
        self,
        role: Union[MessageRole, str],
        content: str,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ChatMessage:
        """
        Add a message to conversation history.
        
        Args:
            role: Message role (user, assistant, system)
            content: Message content
            name: Optional sender name
            metadata: Optional metadata
            
        Returns:
            The created ChatMessage
            
        Example:
            >>> client.add_message(MessageRole.USER, "Hello!")
            >>> client.add_message("assistant", "Hi there!")
        """
        if isinstance(role, str):
            role = MessageRole(role)
        
        message = ChatMessage(
            role=role,
            content=content,
            name=name,
            metadata=metadata or {}
        )
        self._conversation_history.append(message)
        return message
    
    def add_user_message(self, content: str, **kwargs) -> ChatMessage:
        """Add a user message to history."""
        return self.add_message(MessageRole.USER, content, **kwargs)
    
    def add_assistant_message(self, content: str, **kwargs) -> ChatMessage:
        """Add an assistant message to history."""
        return self.add_message(MessageRole.ASSISTANT, content, **kwargs)
    
    def add_system_message(self, content: str, **kwargs) -> ChatMessage:
        """Add a system message to history."""
        return self.add_message(MessageRole.SYSTEM, content, **kwargs)
    
    def clear_history(self) -> None:
        """Clear conversation history."""
        self._conversation_history = []
    
    def get_history(self) -> List[ChatMessage]:
        """Get a copy of conversation history."""
        return list(self._conversation_history)
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """
        Get token usage statistics.
        
        Returns:
            Dictionary with usage statistics including:
            - total_tokens: Total tokens used
            - input_tokens: Input tokens used
            - output_tokens: Output tokens used
            - cache_read_tokens: Tokens read from cache
            - request_count: Number of API requests
            - avg_tokens_per_request: Average tokens per request
        """
        return self._client.get_usage_stats()
    
    def reset_stats(self) -> None:
        """Reset usage statistics."""
        self._client.reset_stats()
    
    def get_system_prompt(self, role: str) -> str:
        """
        Get system prompt for an agent role.
        
        Args:
            role: Agent role (manager, coder, reviewer, tester)
            
        Returns:
            System prompt string
        """
        if hasattr(self._client, 'get_system_prompt'):
            return self._client.get_system_prompt(role)
        return ""
    
    def create_tool_definition(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        mcp_server: str = ""
    ) -> ToolDefinition:
        """
        Create a tool definition for tool calling.
        
        Args:
            name: Tool name
            description: Tool description
            input_schema: JSON Schema for input parameters
            mcp_server: Source MCP server name
            
        Returns:
            ToolDefinition object
        """
        return ToolDefinition(
            name=name,
            description=description,
            input_schema=input_schema,
            mcp_server=mcp_server
        )
    
    def __repr__(self) -> str:
        return f"LLMClient(provider={self.provider}, model={self.model})"


# Convenience functions for quick usage

async def quick_complete(
    prompt: str,
    api_key: Optional[str] = None,
    model: str = "claude-3-5-sonnet-20241022",
    **kwargs
) -> str:
    """
    Quick one-off completion without managing a client.
    
    Args:
        prompt: The prompt to complete
        api_key: API key (uses ANTHROPIC_API_KEY env var if not provided)
        model: Model to use
        **kwargs: Additional parameters
        
    Returns:
        Response content string
        
    Example:
        >>> response = await quick_complete("What is 2+2?")
        >>> print(response)
        "4"
    """
    config = LLMConfig(
        provider="anthropic",
        api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"),
        model=model,
        **kwargs
    )
    client = LLMClient(config)
    response = await client.complete(prompt)
    return response.content


def create_anthropic_client(
    api_key: Optional[str] = None,
    model: str = "claude-3-5-sonnet-20241022",
    **kwargs
) -> LLMClient:
    """
    Create an Anthropic Claude client with sensible defaults.
    
    Args:
        api_key: API key (uses ANTHROPIC_API_KEY env var if not provided)
        model: Claude model to use
        **kwargs: Additional configuration
        
    Returns:
        Configured LLMClient instance
        
    Example:
        >>> client = create_anthropic_client()
        >>> response = await client.complete("Hello!")
    """
    config = LLMConfig(
        provider="anthropic",
        api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"),
        model=model,
        **kwargs
    )
    return LLMClient(config)


# Export public API
__all__ = [
    # Main client class
    "LLMClient",
    
    # Factory functions
    "create_client",
    "create_anthropic_client",
    "quick_complete",
    
    # Provider management
    "register_provider",
    "get_available_providers",
    
    # Type classes
    "BaseLLMClient",
    "ChatMessage",
    "MessageRole",
    "ToolDefinition",
    "ToolUse",
    "LLMResponse",
    "LLMConfig",
    
    # Provider implementations
    "AnthropicClient",
]
