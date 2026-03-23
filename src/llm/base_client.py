"""
LLM Client Base Classes and Interfaces

Defines the base class for LLM clients and common data structures.
Supports multiple providers with unified interface.

As specified in Section 1.2 of the Phase 2 LLM/MCP Integration Specification.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Dict, List, Optional, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class MessageRole(Enum):
    """Message roles in conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class ChatMessage:
    """
    A single message in the conversation.
    
    Attributes:
        role: Message role (system, user, assistant)
        content: Message content text
        name: Optional name for the message sender
        metadata: Additional metadata (e.g., tool uses)
    """
    role: MessageRole
    content: str
    name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "role": self.role.value,
            "content": self.content,
        }
        if self.name:
            result["name"] = self.name
        if self.metadata:
            result["metadata"] = self.metadata
        return result


@dataclass
class ToolDefinition:
    """
    Definition of a tool available to the LLM.
    
    Attributes:
        name: Tool name
        description: Tool description for the LLM
        input_schema: JSON Schema for tool input
        mcp_server: Which MCP server provides this tool
    """
    name: str
    description: str
    input_schema: Dict[str, Any]
    mcp_server: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API calls."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


@dataclass
class ToolUse:
    """
    A tool use request from the LLM.
    
    Attributes:
        id: Unique identifier for this tool use
        name: Name of the tool to call
        input: Input parameters for the tool
    """
    id: str
    name: str
    input: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "input": self.input,
        }


@dataclass
class LLMResponse:
    """
    Response from LLM completion.
    
    Attributes:
        content: Text content of the response
        tool_uses: List of tool use requests (if any)
        stop_reason: Reason for stopping (end_turn, max_tokens, tool_use)
        usage: Token usage statistics
        model: Model used for generation
        finish_reason: Optional finish reason from provider
    """
    content: str
    tool_uses: List[ToolUse] = field(default_factory=list)
    stop_reason: str = "end_turn"
    usage: Dict[str, int] = field(default_factory=dict)
    model: str = ""
    finish_reason: Optional[str] = None
    
    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls."""
        return len(self.tool_uses) > 0


@dataclass
class LLMConfig:
    """
    Configuration for LLM client.
    
    Attributes:
        provider: LLM provider name (anthropic, openai, etc.)
        model: Model identifier
        max_tokens: Maximum tokens in response
        temperature: Sampling temperature
        api_key: API key (can also be set via environment)
        base_url: Optional base URL override
        timeout_seconds: Request timeout
        max_retries: Maximum retry attempts
        retry_backoff_seconds: Backoff time between retries
        enable_caching: Enable prompt caching
        metadata: Additional provider-specific configuration
    """
    provider: str = "anthropic"
    model: str = "claude-3-5-sonnet-20241022"
    max_tokens: int = 4096
    temperature: float = 0.7
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout_seconds: int = 120
    max_retries: int = 3
    retry_backoff_seconds: float = 1.0
    enable_caching: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMConfig":
        """Create config from dictionary."""
        return cls(
            provider=data.get("provider", "anthropic"),
            model=data.get("default_model", data.get("model", "claude-3-5-sonnet-20241022")),
            max_tokens=data.get("max_tokens", 4096),
            temperature=data.get("temperature", 0.7),
            api_key=data.get("api_key"),
            base_url=data.get("base_url"),
            timeout_seconds=data.get("timeout_seconds", 120),
            max_retries=data.get("max_retries", 3),
            retry_backoff_seconds=data.get("retry_backoff_seconds", 1.0),
            enable_caching=data.get("enable_caching", True),
            metadata=data.get("metadata", {}),
        )


class BaseLLMClient(ABC):
    """
    Abstract base class for LLM clients.
    
    Provides unified interface for different LLM providers.
    All provider-specific implementations inherit from this class.
    
    Subclasses must implement:
    - complete(): Synchronous completion
    - stream_complete(): Streaming completion
    
    Features:
    - Token usage tracking
    - Configuration management
    - Provider abstraction
    """
    
    def __init__(self, config: LLMConfig):
        """
        Initialize the LLM client.
        
        Args:
            config: LLM configuration
        """
        self.config = config
        self._total_tokens_used = 0
        self._request_count = 0
        self._input_tokens_used = 0
        self._output_tokens_used = 0
        self._cache_read_tokens = 0
    
    @abstractmethod
    async def complete(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Complete a conversation with the LLM.
        
        Args:
            messages: Conversation history
            tools: Available tools for tool use
            system_prompt: System prompt override
            **kwargs: Additional provider-specific parameters
            
        Returns:
            LLMResponse with content and optional tool uses
        """
        pass
    
    @abstractmethod
    async def stream_complete(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Stream completion response.
        
        Args:
            messages: Conversation history
            tools: Available tools for tool use
            system_prompt: System prompt override
            **kwargs: Additional provider-specific parameters
            
        Yields:
            Text chunks as they arrive
        """
        pass
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """
        Get token usage statistics.
        
        Returns:
            Dictionary with usage statistics
        """
        return {
            "total_tokens": self._total_tokens_used,
            "input_tokens": self._input_tokens_used,
            "output_tokens": self._output_tokens_used,
            "cache_read_tokens": self._cache_read_tokens,
            "request_count": self._request_count,
            "avg_tokens_per_request": (
                self._total_tokens_used / self._request_count 
                if self._request_count > 0 else 0
            )
        }
    
    def _update_usage(self, usage: Dict[str, int]) -> None:
        """
        Update usage statistics.
        
        Args:
            usage: Usage dictionary with token counts
        """
        total = usage.get("total_tokens", 0)
        if total == 0:
            total = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        
        self._total_tokens_used += total
        self._input_tokens_used += usage.get("input_tokens", 0)
        self._output_tokens_used += usage.get("output_tokens", 0)
        self._cache_read_tokens += usage.get("cache_read_tokens", 0)
        self._request_count += 1
        
        logger.debug(
            f"LLM usage updated: +{usage.get('input_tokens', 0)} input, "
            f"+{usage.get('output_tokens', 0)} output tokens"
        )
    
    def reset_stats(self) -> None:
        """Reset usage statistics."""
        self._total_tokens_used = 0
        self._input_tokens_used = 0
        self._output_tokens_used = 0
        self._cache_read_tokens = 0
        self._request_count = 0
