#!/usr/bin/env python3
"""
Test script for Phase 2 LLM Integration.

Verifies that the LLM client abstraction layer and agent integration work correctly.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))


def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")
    
    # Test LLM imports
    from llm import (
        BaseLLMClient,
        ChatMessage,
        MessageRole,
        ToolDefinition,
        ToolUse,
        LLMResponse,
        LLMConfig,
        AnthropicClient,
        create_llm_client,
    )
    print("  ✓ LLM module imports OK")
    
    # Test Agent imports
    from agents import (
        BaseAgent,
        AgentRole,
        AgentState,
        TaskSpec,
        TaskResult,
        SubTask,
        ManagerAgent,
        CoderAgent,
        ReviewerAgent,
    )
    print("  ✓ Agent module imports OK")
    
    return True


def test_llm_types():
    """Test LLM type instantiation."""
    print("\nTesting LLM types...")
    
    from llm import (
        ChatMessage,
        MessageRole,
        ToolDefinition,
        ToolUse,
        LLMResponse,
        LLMConfig,
    )
    
    # Test ChatMessage
    msg = ChatMessage(
        role=MessageRole.USER,
        content="Hello, world!"
    )
    assert msg.role == MessageRole.USER
    assert msg.content == "Hello, world!"
    print("  ✓ ChatMessage works")
    
    # Test ToolDefinition
    tool = ToolDefinition(
        name="test_tool",
        description="A test tool",
        input_schema={"type": "object"},
        mcp_server="test"
    )
    assert tool.name == "test_tool"
    print("  ✓ ToolDefinition works")
    
    # Test ToolUse
    tool_use = ToolUse(
        id="tool_123",
        name="test_tool",
        input={"arg": "value"}
    )
    assert tool_use.id == "tool_123"
    print("  ✓ ToolUse works")
    
    # Test LLMConfig
    config = LLMConfig(
        model="claude-3-5-sonnet-20241022",
        max_tokens=4096,
        temperature=0.7
    )
    assert config.model == "claude-3-5-sonnet-20241022"
    print("  ✓ LLMConfig works")
    
    # Test LLMResponse
    response = LLMResponse(
        content="Response text",
        stop_reason="end_turn",
        usage={"input_tokens": 10, "output_tokens": 5}
    )
    assert response.content == "Response text"
    print("  ✓ LLMResponse works")
    
    return True


def test_agent_types():
    """Test agent type instantiation."""
    print("\nTesting agent types...")
    
    from agents import (
        AgentRole,
        AgentState,
        TaskSpec,
        SubTask,
    )
    
    # Test AgentRole
    assert AgentRole.MANAGER.value == "manager"
    assert AgentRole.CODER.value == "coder"
    assert AgentRole.REVIEWER.value == "reviewer"
    print("  ✓ AgentRole enum works")
    
    # Test AgentState
    assert AgentState.IDLE.value == "idle"
    assert AgentState.ACTIVE.value == "active"
    print("  ✓ AgentState enum works")
    
    # Test TaskSpec
    task = TaskSpec(
        task_id="task_123",
        task_type="implement",
        specification="Implement feature X"
    )
    assert task.task_id == "task_123"
    print("  ✓ TaskSpec works")
    
    # Test SubTask
    subtask = SubTask(
        parent_task_id="task_123",
        name="Subtask 1",
        description="Do something"
    )
    assert subtask.parent_task_id == "task_123"
    print("  ✓ SubTask works")
    
    return True


def test_anthropic_client():
    """Test AnthropicClient instantiation."""
    print("\nTesting AnthropicClient...")
    
    from llm import AnthropicClient, LLMConfig
    
    # Test client creation
    config = LLMConfig(
        api_key="test_key",  # Mock key for testing
        model="claude-3-5-sonnet-20241022"
    )
    client = AnthropicClient(config)
    
    assert client.config.model == "claude-3-5-sonnet-20241022"
    assert client._total_tokens_used == 0
    print("  ✓ AnthropicClient instantiation works")
    
    # Test usage stats
    stats = client.get_usage_stats()
    assert stats["request_count"] == 0
    print("  ✓ get_usage_stats works")
    
    # Test system prompts
    for role in ["manager", "coder", "reviewer", "tester"]:
        prompt = AnthropicClient.get_system_prompt(role)
        assert isinstance(prompt, str)
        assert len(prompt) > 0
    print("  ✓ get_system_prompt works for all roles")
    
    return True


async def test_agent_llm_integration():
    """Test agent LLM integration."""
    print("\nTesting agent LLM integration...")
    
    from agents import ManagerAgent, CoderAgent, ReviewerAgent
    from llm import LLMConfig
    
    # Test ManagerAgent
    manager = ManagerAgent(
        agent_id="test_manager",
        repo_root="/tmp"
    )
    assert manager.role.value == "manager"
    assert manager._llm_client is None  # Not initialized yet
    print("  ✓ ManagerAgent instantiation works")
    
    # Test CoderAgent
    coder = CoderAgent(
        agent_id="test_coder",
        repo_root="/tmp"
    )
    assert coder.role.value == "coder"
    print("  ✓ CoderAgent instantiation works")
    
    # Test ReviewerAgent
    reviewer = ReviewerAgent(
        agent_id="test_reviewer",
        repo_root="/tmp"
    )
    assert reviewer.role.value == "reviewer"
    print("  ✓ ReviewerAgent instantiation works")
    
    # Test with LLM config
    config = LLMConfig(api_key="test_key")
    coder_with_config = CoderAgent(
        agent_id="coder_config",
        repo_root="/tmp",
        llm_config=config  # This parameter now exists in Phase 2
    )
    # The config is stored but client not initialized until initialize() is called
    print("  ✓ Agent with LLMConfig instantiation works")
    
    return True


def run_tests():
    """Run all tests."""
    print("=" * 60)
    print("AutoDev Phase 2 LLM Integration Tests")
    print("=" * 60)
    
    all_passed = True
    
    try:
        all_passed = test_imports() and all_passed
        all_passed = test_llm_types() and all_passed
        all_passed = test_agent_types() and all_passed
        all_passed = test_anthropic_client() and all_passed
        all_passed = asyncio.run(test_agent_llm_integration()) and all_passed
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All Phase 2 LLM Integration tests passed!")
    else:
        print("❌ Some tests failed")
    print("=" * 60)
    
    return all_passed


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
