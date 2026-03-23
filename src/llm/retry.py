"""
LLM Client Retry Logic

Implements exponential backoff retry mechanism for LLM API calls.
Handles transient errors gracefully with configurable retry policies.
"""

import asyncio
import random
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional, TypeVar, Any, List, Type, Tuple
from functools import wraps

from .exceptions import (
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMServiceUnavailableError,
    LLMOverloadedError,
    LLMConnectionError,
)

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class RetryConfig:
    """
    Configuration for retry behavior.
    
    Attributes:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        exponential_base: Base for exponential backoff calculation
        jitter: Whether to add random jitter to delays
        jitter_range: Range for jitter (0.0 to 1.0)
        retryable_exceptions: List of exception types to retry
        retryable_status_codes: HTTP status codes that should trigger retry
    """
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_range: float = 0.1
    retryable_exceptions: Tuple[Type[Exception], ...] = (
        LLMRateLimitError,
        LLMTimeoutError,
        LLMServiceUnavailableError,
        LLMOverloadedError,
        LLMConnectionError,
    )
    retryable_status_codes: Tuple[int, ...] = (408, 429, 500, 502, 503, 529)
    
    def calculate_delay(self, attempt: int, retry_after: Optional[float] = None) -> float:
        """
        Calculate delay for a given retry attempt.
        
        Args:
            attempt: The retry attempt number (0-indexed)
            retry_after: Optional server-suggested retry delay
            
        Returns:
            Delay in seconds
        """
        # Use server-suggested delay if available
        if retry_after is not None:
            delay = min(retry_after, self.max_delay)
        else:
            # Calculate exponential backoff
            delay = self.base_delay * (self.exponential_base ** attempt)
            delay = min(delay, self.max_delay)
        
        # Add jitter to prevent thundering herd
        if self.jitter and delay > 0:
            jitter_amount = delay * self.jitter_range
            delay += random.uniform(-jitter_amount, jitter_amount)
        
        return max(0, delay)


class RetryHandler:
    """
    Handles retry logic for LLM API calls.
    
    Provides:
    - Exponential backoff with configurable parameters
    - Jitter to prevent thundering herd
    - Respects Retry-After headers
    - Logs retry attempts
    - Tracks retry statistics
    """
    
    def __init__(self, config: Optional[RetryConfig] = None):
        """
        Initialize retry handler.
        
        Args:
            config: Retry configuration (uses defaults if not provided)
        """
        self.config = config or RetryConfig()
        self._total_retries = 0
        self._successful_retries = 0
        self._failed_after_retries = 0
    
    def is_retryable(self, error: Exception) -> bool:
        """
        Check if an error is retryable.
        
        Args:
            error: The exception to check
            
        Returns:
            True if the error is retryable
        """
        # Check if it's a retryable exception type
        if isinstance(error, self.config.retryable_exceptions):
            return True
        
        # Check for retryable status codes in LLMError
        if isinstance(error, LLMError):
            status_code = error.details.get('status_code')
            if status_code in self.config.retryable_status_codes:
                return True
        
        # Check for common network errors
        error_name = type(error).__name__
        retryable_error_names = {
            'ConnectionError',
            'TimeoutError',
            'ConnectTimeout',
            'ReadTimeout',
            'ConnectionResetError',
            'BrokenPipeError',
        }
        if error_name in retryable_error_names:
            return True
        
        return False
    
    def get_retry_after(self, error: Exception) -> Optional[float]:
        """
        Get suggested retry delay from an error.
        
        Args:
            error: The exception to extract retry-after from
            
        Returns:
            Retry delay in seconds, or None
        """
        if isinstance(error, LLMRateLimitError) and error.retry_after:
            return error.retry_after
        if isinstance(error, LLMServiceUnavailableError) and error.retry_after:
            return error.retry_after
        if isinstance(error, LLMOverloadedError) and error.retry_after:
            return error.retry_after
        return None
    
    async def execute_with_retry(
        self,
        func: Callable[..., T],
        *args,
        **kwargs
    ) -> T:
        """
        Execute a function with retry logic.
        
        Args:
            func: Async function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Function result
            
        Raises:
            LLMError: If all retries are exhausted
        """
        last_error: Optional[Exception] = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
                    
            except Exception as e:
                last_error = e
                
                # Check if we should retry
                if attempt >= self.config.max_retries:
                    self._failed_after_retries += 1
                    logger.error(
                        f"All {self.config.max_retries} retries exhausted. "
                        f"Last error: {e}"
                    )
                    raise
                
                if not self.is_retryable(e):
                    logger.error(f"Non-retryable error: {e}")
                    raise
                
                # Calculate delay
                retry_after = self.get_retry_after(e)
                delay = self.config.calculate_delay(attempt, retry_after)
                
                self._total_retries += 1
                
                logger.warning(
                    f"Retryable error on attempt {attempt + 1}/{self.config.max_retries + 1}: {e}. "
                    f"Retrying in {delay:.2f}s..."
                )
                
                # Wait before retry
                if delay > 0:
                    await asyncio.sleep(delay)
        
        # Should never reach here, but just in case
        if last_error:
            raise last_error
        raise RuntimeError("Unexpected state in retry handler")
    
    def get_stats(self) -> dict:
        """
        Get retry statistics.
        
        Returns:
            Dictionary with retry statistics
        """
        return {
            "total_retries": self._total_retries,
            "successful_retries": self._successful_retries,
            "failed_after_retries": self._failed_after_retries,
        }
    
    def reset_stats(self) -> None:
        """Reset retry statistics."""
        self._total_retries = 0
        self._successful_retries = 0
        self._failed_after_retries = 0


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
):
    """
    Decorator to add retry logic to async functions.
    
    Args:
        max_retries: Maximum retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
        jitter: Whether to add random jitter
        
    Returns:
        Decorated function with retry logic
        
    Example:
        @with_retry(max_retries=3, base_delay=1.0)
        async def call_api():
            # Make API call
            pass
    """
    config = RetryConfig(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=max_delay,
        exponential_base=exponential_base,
        jitter=jitter,
    )
    handler = RetryHandler(config)
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await handler.execute_with_retry(func, *args, **kwargs)
        return wrapper
    
    return decorator


__all__ = [
    "RetryConfig",
    "RetryHandler",
    "with_retry",
]
