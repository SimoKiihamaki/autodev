"""
LLM Client Exceptions

Custom exception classes for LLM client error handling.
Provides granular error handling for different failure scenarios.
"""

from typing import Optional, Dict, Any


class LLMError(Exception):
    """Base exception for all LLM-related errors."""
    
    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.model = model
        self.details = details or {}
    
    def __str__(self) -> str:
        parts = [self.message]
        if self.provider:
            parts.append(f"provider={self.provider}")
        if self.model:
            parts.append(f"model={self.model}")
        return " | ".join(parts)


class LLMConfigurationError(LLMError):
    """Raised when LLM client configuration is invalid."""
    
    def __init__(self, message: str, config_key: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.config_key = config_key


class LLMConnectionError(LLMError):
    """Raised when connection to LLM provider fails."""
    
    def __init__(
        self,
        message: str,
        original_error: Optional[Exception] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.original_error = original_error


class LLMRateLimitError(LLMError):
    """
    Raised when rate limit is exceeded.
    
    Attributes:
        retry_after: Suggested wait time in seconds before retry
    """
    
    def __init__(
        self,
        message: str,
        retry_after: Optional[float] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class LLMAuthenticationError(LLMError):
    """Raised when authentication with LLM provider fails."""
    
    def __init__(self, message: str = "Authentication failed", **kwargs):
        super().__init__(message, **kwargs)


class LLMModelNotFoundError(LLMError):
    """Raised when the specified model is not available."""
    
    def __init__(self, model: str, available_models: Optional[list] = None, **kwargs):
        message = f"Model '{model}' not found"
        if available_models:
            message += f". Available models: {', '.join(available_models)}"
        super().__init__(message, model=model, **kwargs)
        self.available_models = available_models


class LLMContextLengthError(LLMError):
    """Raised when the context length exceeds the model's limit."""
    
    def __init__(
        self,
        message: str = "Context length exceeded",
        token_count: Optional[int] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.token_count = token_count
        self.max_tokens = max_tokens


class LLMResponseError(LLMError):
    """Raised when LLM response is invalid or cannot be parsed."""
    
    def __init__(
        self,
        message: str,
        response_data: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.response_data = response_data


class LLMToolUseError(LLMError):
    """Raised when tool use fails."""
    
    def __init__(
        self,
        message: str,
        tool_name: Optional[str] = None,
        tool_id: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.tool_name = tool_name
        self.tool_id = tool_id


class LLMTimeoutError(LLMError):
    """Raised when LLM request times out."""
    
    def __init__(
        self,
        message: str = "Request timed out",
        timeout_seconds: Optional[float] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.timeout_seconds = timeout_seconds


class LLMContentFilterError(LLMError):
    """Raised when content is filtered by the provider's safety systems."""
    
    def __init__(
        self,
        message: str = "Content filtered by safety systems",
        reason: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.reason = reason


class LLMServiceUnavailableError(LLMError):
    """Raised when LLM service is temporarily unavailable."""
    
    def __init__(
        self,
        message: str = "Service temporarily unavailable",
        retry_after: Optional[float] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class LLMOverloadedError(LLMError):
    """Raised when the LLM provider is overloaded."""
    
    def __init__(
        self,
        message: str = "Provider overloaded",
        retry_after: Optional[float] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


# Mapping of HTTP status codes to exception classes
HTTP_STATUS_TO_EXCEPTION = {
    400: LLMResponseError,
    401: LLMAuthenticationError,
    403: LLMAuthenticationError,
    404: LLMModelNotFoundError,
    408: LLMTimeoutError,
    413: LLMContextLengthError,
    429: LLMRateLimitError,
    500: LLMServiceUnavailableError,
    502: LLMServiceUnavailableError,
    503: LLMServiceUnavailableError,
    529: LLMOverloadedError,
}


def get_exception_for_status(
    status_code: int,
    message: str,
    **kwargs
) -> LLMError:
    """
    Get the appropriate exception class for an HTTP status code.
    
    Args:
        status_code: HTTP status code
        message: Error message
        **kwargs: Additional arguments for the exception
        
    Returns:
        Appropriate LLMError subclass
    """
    exception_class = HTTP_STATUS_TO_EXCEPTION.get(status_code, LLMError)
    return exception_class(message, **kwargs)


__all__ = [
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
]
