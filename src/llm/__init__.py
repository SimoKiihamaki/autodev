"""
AutoDev LLM Client Layer

Provides abstraction over LLM providers with Anthropic Claude implementation.
Phase 2: Provider abstraction with factory pattern.
Phase 3: Enhanced error handling, retries, and response parsing.

Main entry point: LLMClient class from client.py

Usage:
    from llm import LLMClient, LLMConfig
    
    config = LLMConfig(api_key="sk-ant-...")
    client = LLMClient(config)
    response = await client.complete("Hello!")
"""

# Import main client interface
from .client import (
    LLMClient,
    create_client,
    create_anthropic_client,
    quick_complete,
    register_provider,
    get_available_providers,
)

# Import base types
from .base_client import (
    BaseLLMClient,
    ChatMessage,
    MessageRole,
    ToolDefinition,
    ToolUse,
    LLMResponse,
    LLMConfig,
)

# Import provider implementations
from .anthropic_client import AnthropicClient, AnthropicLLMClient

# Import exceptions (Phase 3)
from .exceptions import (
    LLMError,
    LLMConfigurationError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMAuthenticationError,
    LLMModelNotFoundError,
    LLMContextLengthError,
    LLMResponseError,
    LLMToolUseError,
    LLMTimeoutError,
    LLMContentFilterError,
    LLMServiceUnavailableError,
    LLMOverloadedError,
    get_exception_for_status,
)

# Import retry handling (Phase 3)
from .retry import (
    RetryConfig,
    RetryHandler,
    with_retry,
)

# Import response parsing (Phase 3)
from .response_parser import (
    ParsedContent,
    ResponseParser,
    StreamingResponseParser,
)


# Legacy alias for backward compatibility
def create_llm_client(config: LLMConfig) -> BaseLLMClient:
    """
    Factory function to create an LLM client based on configuration.
    
    Deprecated: Use create_client() or LLMClient directly.
    
    Args:
        config: LLM configuration
        
    Returns:
        Appropriate LLM client instance
    """
    return create_client(config)


__all__ = [
    # Main client class (primary interface)
    "LLMClient",
    
    # Factory functions
    "create_client",
    "create_llm_client",  # Legacy alias
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
    "AnthropicLLMClient",  # Alias
    
    # Exceptions (Phase 3)
    "LLMError",
    "LLMConfigurationError",
    "LLMConnectionError",
    "LLMRateLimitError",
    "LLMAuthenticationError",
    "LLMModelNotFoundError",
    "LLMContextLengthError",
    "LLMResponseError",
    "LLMToolUseError",
    "LLMTimeoutError",
    "LLMContentFilterError",
    "LLMServiceUnavailableError",
    "LLMOverloadedError",
    "get_exception_for_status",
    
    # Retry handling (Phase 3)
    "RetryConfig",
    "RetryHandler",
    "with_retry",
    
    # Response parsing (Phase 3)
    "ParsedContent",
    "ResponseParser",
    "StreamingResponseParser",
]
