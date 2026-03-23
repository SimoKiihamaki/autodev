# AutoDev Phase 3: LLM Client Integration - Quick Reference

**Version:** 3.0.0  
**Created:** 2026-03-23  
**Status:** Implemented  

---

## Overview

Phase 3 enhances the LLM client abstraction layer with:
- **Custom Exceptions**: Granular error handling for different failure scenarios
- **Retry Logic**: Exponential backoff with jitter for transient errors
- **Response Parsing**: Robust parsing for different response formats

---

## New Modules

### 1. Exceptions (`src/llm/exceptions.py`)

Custom exception hierarchy for LLM errors:

```python
from llm import (
    LLMError,               # Base exception
    LLMConfigurationError,  # Invalid configuration
    LLMConnectionError,     # Connection failures
    LLMRateLimitError,      # Rate limit exceeded (has retry_after)
    LLMAuthenticationError, # Auth failures
    LLMModelNotFoundError,  # Model not available
    LLMContextLengthError,  # Context too long
    LLMResponseError,       # Invalid response
    LLMToolUseError,        # Tool use failures
    LLMTimeoutError,        # Request timeout
    LLMContentFilterError,  # Content filtered
    LLMServiceUnavailableError,  # Service down
    LLMOverloadedError,     # Provider overloaded
)
```

**Example:**
```python
try:
    response = await client.complete(messages)
except LLMRateLimitError as e:
    wait_time = e.retry_after or 30
    await asyncio.sleep(wait_time)
except LLMContextLengthError:
    # Reduce message count
    messages = messages[-5:]
```

### 2. Retry Handler (`src/llm/retry.py`)

Configurable retry with exponential backoff:

```python
from llm import RetryConfig, RetryHandler, with_retry

# Configure retry behavior
config = RetryConfig(
    max_retries=3,
    base_delay=1.0,        # Initial delay
    max_delay=60.0,        # Maximum delay
    exponential_base=2.0,  # 1s, 2s, 4s, etc.
    jitter=True,           # Add randomness
)

# Use with handler
handler = RetryHandler(config)
result = await handler.execute_with_retry(some_async_function)

# Or use decorator
@with_retry(max_retries=3, base_delay=1.0)
async def call_api():
    ...
```

### 3. Response Parser (`src/llm/response_parser.py`)

Parse LLM responses for structured content:

```python
from llm import ResponseParser, ParsedContent

parser = ResponseParser()

# Parse text for code blocks, JSON, etc.
parsed = parser.parse_content(response.content)

if parsed.has_code():
    code = parsed.get_code(language="python")
    
if parsed.structured_data:
    data = parsed.structured_data
```

---

## Enhanced AnthropicClient

The `AnthropicClient` now includes:

1. **Configuration Validation**
   - Validates `max_tokens`, `temperature`, etc.
   - Raises `LLMConfigurationError` for invalid config

2. **Automatic Retry**
   - Retries on rate limits, timeouts, service errors
   - Respects `Retry-After` headers
   - Tracks retry statistics

3. **Better Error Mapping**
   - Maps API status codes to specific exceptions
   - Preserves error context

**New Methods:**
```python
client = AnthropicClient(config)

# Get retry statistics
stats = client.get_retry_stats()
# {'total_retries': 2, 'successful_retries': 2, 'failed_after_retries': 0}

# Reset statistics
client.reset_retry_stats()

# Create tool result message (convenience)
msg = client.create_tool_result_message(
    tool_use_id="tool_123",
    content="Result here",
    is_error=False
)
```

---

## Backward Compatibility

All Phase 2 code continues to work:
- `LLMClient` class unchanged
- `create_client()` factory works
- All type classes (`ChatMessage`, `ToolDefinition`, etc.) unchanged

---

## Files Created/Modified

| File | Status | Description |
|------|--------|-------------|
| `src/llm/exceptions.py` | New | Custom exception classes |
| `src/llm/retry.py` | New | Retry handler with backoff |
| `src/llm/response_parser.py` | New | Response parsing utilities |
| `src/llm/anthropic_client.py` | Updated | Enhanced with Phase 3 features |
| `src/llm/__init__.py` | Updated | Exports new modules |
| `src/test_phase3_llm.py` | New | Phase 3 test suite |

---

## Usage Examples

### Basic Usage with Error Handling

```python
from llm import LLMClient, LLMConfig, LLMRateLimitError, LLMTimeoutError

config = LLMConfig(api_key="sk-ant-...")
client = LLMClient(config)

try:
    response = await client.complete("Write a function")
except LLMRateLimitError as e:
    print(f"Rate limited. Wait {e.retry_after}s")
except LLMTimeoutError:
    print("Request timed out")
```

### With Custom Retry Config

```python
from llm import LLMConfig, RetryConfig
from llm.anthropic_client import AnthropicClient

config = LLMConfig(
    api_key="sk-ant-...",
    max_retries=5,
    retry_backoff_seconds=2.0,
)

client = AnthropicClient(config)
```

### Parsing Response Content

```python
from llm import ResponseParser

parser = ResponseParser()
parsed = parser.parse_content(response.content)

# Extract code
for block in parsed.code_blocks:
    print(f"Language: {block['language']}")
    print(f"Code: {block['code']}")

# Extract JSON
if parsed.structured_data:
    print(f"Found JSON: {parsed.structured_data}")
```

---

## Running Tests

```bash
# Phase 2 tests (backward compatibility)
python3 src/test_phase2_llm.py

# Phase 3 tests (new features)
python3 src/test_phase3_llm.py
```

---

## Next Steps

Phase 3 is complete. Consider for Phase 4:
- Additional LLM providers (OpenAI, DeepSeek)
- Response caching
- Token counting utilities
- Cost tracking

---

**Last Updated:** 2026-03-23
