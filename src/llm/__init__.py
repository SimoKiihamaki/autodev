"""
AutoDev LLM Client Layer

Provides abstraction over LLM providers with Anthropic Claude implementation.
Phase 2: Provider abstraction with factory pattern.
"""

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

__all__ = [
    "BaseLLMClient",
    "ChatMessage",
    "MessageRole",
    "ToolDefinition",
    "ToolUse",
    "LLMResponse",
    "LLMConfig",
    "AnthropicClient",
    "create_llm_client",
]


def create_llm_client(config: LLMConfig) -> BaseLLMClient:
    """
    Factory function to create an LLM client based on configuration.
    
    Args:
        config: LLM configuration
        
    Returns:
        Appropriate LLM client instance
        
    Raises:
        ValueError: If provider is not supported
    """
    provider = config.provider.lower()
    
    if provider == "anthropic":
        return AnthropicClient(config)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
