"""
AutoDev LLM Client Layer

Provides abstraction over LLM providers with Anthropic Claude implementation.
Phase 2: Provider abstraction with factory pattern.

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
from .anthropic_client import AnthropicClient


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
]
