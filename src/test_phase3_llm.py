#!/usr/bin/env python3
"""
Test script for Phase 3 LLM Client Integration.

Verifies that the enhanced LLM client with error handling, retries,
and response parsing works correctly.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))


def test_exception_imports():
    """Test that all exception classes can be imported."""
    print("Testing exception imports...")
    
    from llm import (
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
    print("  ✓ All exception imports OK")
    
    # Test exception creation
    err = LLMError("Test error", provider="anthropic", model="claude-3")
    assert str(err) == "Test error | provider=anthropic | model=claude-3"
    print("  ✓ LLMError creation works")
    
    # Test rate limit error with retry_after
    rate_err = LLMRateLimitError("Rate limited", retry_after=30.0)
    assert rate_err.retry_after == 30.0
    print("  ✓ LLMRateLimitError with retry_after works")
    
    # Test get_exception_for_status
    exc = get_exception_for_status(429, "Too many requests")
    assert isinstance(exc, LLMRateLimitError)
    print("  ✓ get_exception_for_status works")
    
    return True


def test_retry_imports():
    """Test retry module imports."""
    print("\nTesting retry module imports...")
    
    from llm import RetryConfig, RetryHandler, with_retry, LLMRateLimitError
    print("  ✓ Retry module imports OK")
    
    # Test RetryConfig
    config = RetryConfig(
        max_retries=5,
        base_delay=2.0,
        max_delay=120.0,
        exponential_base=2.0,
        jitter=True,
    )
    assert config.max_retries == 5
    print("  ✓ RetryConfig creation works")
    
    # Test delay calculation
    delay = config.calculate_delay(0)
    assert 0 < delay < 5  # Should be around base_delay with jitter
    print("  ✓ RetryConfig.calculate_delay works")
    
    # Test with retry_after (jitter is still applied)
    delay = config.calculate_delay(0, retry_after=10.0)
    assert 9.0 < delay < 11.0  # Jitter range
    print("  ✓ RetryConfig.calculate_delay with retry_after works")
    
    # Test exponential backoff
    delay_0 = config.calculate_delay(0)
    delay_1 = config.calculate_delay(1)
    delay_2 = config.calculate_delay(2)
    assert delay_1 > delay_0
    assert delay_2 > delay_1
    print("  ✓ Exponential backoff works")
    
    # Test RetryHandler
    handler = RetryHandler(config)
    assert handler.is_retryable(LLMRateLimitError("Test"))
    print("  ✓ RetryHandler.is_retryable works")
    
    return True


def test_response_parser_imports():
    """Test response parser module imports."""
    print("\nTesting response parser imports...")
    
    from llm import ParsedContent, ResponseParser, StreamingResponseParser
    print("  ✓ Response parser imports OK")
    
    # Test ParsedContent
    content = ParsedContent(text="Hello")
    assert content.text == "Hello"
    assert not content.has_code()
    assert not content.has_tool_calls()
    print("  ✓ ParsedContent creation works")
    
    # Test ResponseParser
    parser = ResponseParser()
    print("  ✓ ResponseParser creation works")
    
    # Test code block extraction
    text = """Here's some code:
```python
print("Hello, world!")
```
That's it!"""
    
    parsed = parser.parse_content(text)
    assert len(parsed.code_blocks) == 1
    assert parsed.code_blocks[0]['language'] == 'python'
    assert 'print' in parsed.code_blocks[0]['code']
    print("  ✓ Code block extraction works")
    
    # Test JSON extraction
    json_text = 'Here is JSON: {"key": "value"} end'
    parsed = parser.parse_content(json_text)
    assert parsed.structured_data is not None
    assert parsed.structured_data.get('key') == 'value'
    print("  ✓ JSON extraction works")
    
    return True


def test_anthropic_client_enhancements():
    """Test AnthropicClient Phase 3 enhancements."""
    print("\nTesting AnthropicClient Phase 3 enhancements...")
    
    from llm import AnthropicClient, AnthropicLLMClient, LLMConfig, LLMConfigurationError
    
    # Test that AnthropicLLMClient is an alias
    assert AnthropicLLMClient is AnthropicClient
    print("  ✓ AnthropicLLMClient alias works")
    
    # Test configuration validation
    try:
        config = LLMConfig(
            api_key="sk-ant-test",
            max_tokens=0  # Invalid
        )
        client = AnthropicClient(config)
        print("  ❌ Should have raised LLMConfigurationError")
        return False
    except LLMConfigurationError as e:
        assert 'max_tokens' in str(e)
        print("  ✓ Configuration validation works")
    
    # Test valid configuration
    config = LLMConfig(
        api_key="sk-ant-test",
        max_tokens=1024,
        temperature=0.7
    )
    client = AnthropicClient(config)
    
    # Test retry stats
    stats = client.get_retry_stats()
    assert 'total_retries' in stats
    print("  ✓ get_retry_stats works")
    
    # Test reset_retry_stats
    client.reset_retry_stats()
    stats = client.get_retry_stats()
    assert stats['total_retries'] == 0
    print("  ✓ reset_retry_stats works")
    
    return True


def test_backward_compatibility():
    """Test that Phase 2 functionality still works."""
    print("\nTesting backward compatibility...")
    
    from llm import (
        LLMClient,
        LLMConfig,
        ChatMessage,
        MessageRole,
        ToolDefinition,
        ToolUse,
        LLMResponse,
        AnthropicClient,
        create_client,
        create_anthropic_client,
    )
    print("  ✓ All Phase 2 imports still work")
    
    # Test LLMClient
    config = LLMConfig(api_key="sk-ant-test")
    client = LLMClient(config)
    assert client.provider == "anthropic"
    print("  ✓ LLMClient creation still works")
    
    # Test ChatMessage
    msg = ChatMessage(role=MessageRole.USER, content="Test")
    assert msg.content == "Test"
    print("  ✓ ChatMessage still works")
    
    # Test ToolDefinition
    tool = ToolDefinition(
        name="test",
        description="Test tool",
        input_schema={"type": "object"}
    )
    assert tool.name == "test"
    print("  ✓ ToolDefinition still works")
    
    # Test LLMResponse
    response = LLMResponse(content="Test response")
    assert response.content == "Test response"
    print("  ✓ LLMResponse still works")
    
    return True


async def test_retry_handler_async():
    """Test retry handler with async functions."""
    print("\nTesting async retry handler...")
    
    from llm import RetryHandler, RetryConfig, LLMRateLimitError
    
    config = RetryConfig(max_retries=3, base_delay=0.1)
    handler = RetryHandler(config)
    
    call_count = 0
    
    async def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise LLMRateLimitError("Rate limited", retry_after=0.05)
        return "success"
    
    result = await handler.execute_with_retry(failing_func)
    assert result == "success"
    assert call_count == 3
    print("  ✓ Retry handler with async function works")
    
    # Test with non-retryable error
    call_count = 0
    
    async def non_retryable_func():
        nonlocal call_count
        call_count += 1
        raise ValueError("Not retryable")
    
    try:
        await handler.execute_with_retry(non_retryable_func)
        print("  ❌ Should have raised ValueError")
        return False
    except ValueError:
        assert call_count == 1
        print("  ✓ Non-retryable errors are not retried")
    
    return True


def run_tests():
    """Run all tests."""
    print("=" * 60)
    print("AutoDev Phase 3 LLM Client Integration Tests")
    print("=" * 60)
    
    all_passed = True
    
    try:
        all_passed = test_exception_imports() and all_passed
        all_passed = test_retry_imports() and all_passed
        all_passed = test_response_parser_imports() and all_passed
        all_passed = test_anthropic_client_enhancements() and all_passed
        all_passed = test_backward_compatibility() and all_passed
        all_passed = asyncio.run(test_retry_handler_async()) and all_passed
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All Phase 3 LLM Client Integration tests passed!")
    else:
        print("❌ Some tests failed")
    print("=" * 60)
    
    return all_passed


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
