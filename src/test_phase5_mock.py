#!/usr/bin/env python3
"""
Phase 5 Quick Integration Test (Mock Mode)

Tests the integration layer without requiring real API credentials.
Validates the structure and flow of the LLM ↔ MCP integration.

Run with: python test_phase5_mock.py
"""

import asyncio
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))


def print_header(text: str) -> None:
    """Print a formatted header."""
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")


def print_result(name: str, success: bool, details: str = "") -> None:
    """Print test result."""
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status} - {name}")
    if details:
        print(f"    {details}")


def test_imports():
    """Test that all modules can be imported."""
    print_header("Test 1: Module Imports")
    
    try:
        # Test integration module
        from integration import (
            AutoDevPipeline,
            CoderPipeline,
            PipelineConfig,
            ExecutionResult,
            quick_code,
            create_coder_pipeline,
        )
        print_result("Integration module imports", True)
        
        # Test LLM module
        from llm.client import LLMClient, LLMConfig
        from llm.base_client import ChatMessage, MessageRole, ToolDefinition
        print_result("LLM module imports", True)
        
        # Test MCP module
        from mcp.client import AutoDevMCPClient, MCPServerConfig
        print_result("MCP module imports", True)
        
        # Test tool executor
        from agents.tool_executor import ToolExecutionLoop
        print_result("Tool executor imports", True)
        
        # Test agents
        from agents.base import BaseAgent, AgentRole, AgentState
        print_result("Agent module imports", True)
        
        return True
        
    except Exception as e:
        print_result("Module imports", False, str(e))
        import traceback
        traceback.print_exc()
        return False


def test_data_structures():
    """Test data structure creation."""
    print_header("Test 2: Data Structures")
    
    try:
        from integration import PipelineConfig, ExecutionResult
        from llm.base_client import LLMConfig, ChatMessage, MessageRole, ToolDefinition
        from mcp.client import MCPServerConfig, MCPSecurityConfig
        from agents.base import TaskSpec, TaskResult, SubTask
        
        # Test LLMConfig
        llm_config = LLMConfig(
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            api_key="test-key"
        )
        print_result("LLMConfig creation", True, f"model={llm_config.model}")
        
        # Test ChatMessage
        msg = ChatMessage(
            role=MessageRole.USER,
            content="Hello, world!"
        )
        print_result("ChatMessage creation", True, f"role={msg.role.value}")
        
        # Test ToolDefinition
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object"},
            mcp_server="test"
        )
        print_result("ToolDefinition creation", True, f"name={tool.name}")
        
        # Test MCPServerConfig
        server_config = MCPServerConfig(
            name="test-server",
            command="test-command",
            args=["--test"],
            enabled=True
        )
        print_result("MCPServerConfig creation", True, f"name={server_config.name}")
        
        # Test MCPSecurityConfig
        security_config = MCPSecurityConfig(
            allowed_paths=["/workspace"],
            allow_all_paths=True
        )
        print_result("MCPSecurityConfig creation", True)
        
        # Test PipelineConfig
        pipeline_config = PipelineConfig(
            max_tool_iterations=10,
            workspace_path="/tmp/test"
        )
        print_result("PipelineConfig creation", True, f"iterations={pipeline_config.max_tool_iterations}")
        
        # Test ExecutionResult
        result = ExecutionResult(
            success=True,
            content="Test content",
            iterations=3,
            tools_called=[{"name": "test"}]
        )
        print_result("ExecutionResult creation", True, f"success={result.success}")
        
        # Test TaskSpec
        task_spec = TaskSpec(
            task_type="implement",
            specification="Create a test"
        )
        print_result("TaskSpec creation", True, f"type={task_spec.task_type}")
        
        return True
        
    except Exception as e:
        print_result("Data structures", False, str(e))
        import traceback
        traceback.print_exc()
        return False


def test_pipeline_creation():
    """Test pipeline object creation (without initialization)."""
    print_header("Test 3: Pipeline Creation")
    
    try:
        from integration import AutoDevPipeline, CoderPipeline, PipelineConfig
        from llm.base_client import LLMConfig
        
        # Test AutoDevPipeline creation
        config = PipelineConfig(
            llm_config=LLMConfig(api_key="test-key"),
            max_tool_iterations=15
        )
        pipeline = AutoDevPipeline(config)
        
        assert pipeline.config is not None
        assert pipeline._llm_client is None  # Not initialized yet
        assert pipeline._mcp_client is None
        assert not pipeline._initialized
        
        print_result("AutoDevPipeline creation", True)
        
        # Test CoderPipeline creation
        coder_pipeline = CoderPipeline(config)
        
        assert isinstance(coder_pipeline, AutoDevPipeline)
        assert hasattr(coder_pipeline, '_get_default_system_prompt')
        
        # Check system prompt
        system_prompt = coder_pipeline._get_default_system_prompt()
        assert "developer" in system_prompt.lower() or "code" in system_prompt.lower()
        
        print_result("CoderPipeline creation", True, "Has specialized system prompt")
        
        return True
        
    except Exception as e:
        print_result("Pipeline creation", False, str(e))
        import traceback
        traceback.print_exc()
        return False


def test_convenience_functions():
    """Test convenience function creation."""
    print_header("Test 4: Convenience Functions")
    
    try:
        from integration import create_coder_pipeline
        
        # Test create_coder_pipeline
        pipeline = create_coder_pipeline(
            api_key="test-key",
            workspace="/tmp/test",
            max_iterations=10
        )
        
        assert pipeline is not None
        assert not pipeline._initialized
        assert pipeline.config.max_tool_iterations == 10
        
        print_result("create_coder_pipeline", True)
        
        return True
        
    except Exception as e:
        print_result("Convenience functions", False, str(e))
        import traceback
        traceback.print_exc()
        return False


def test_mcp_client_mock():
    """Test MCP client mock mode."""
    print_header("Test 5: MCP Client Mock Mode")
    
    try:
        from mcp.client import AutoDevMCPClient
        from agents.tool_executor import MockMCPClient
        
        # Test MockMCPClient
        mock_client = MockMCPClient()
        
        # Should have mock tools
        tools = mock_client.get_tools_for_llm()
        assert len(tools) > 0, "Mock client should have tools"
        
        print_result("MockMCPClient creation", True, f"{len(tools)} mock tools available")
        
        # Test tool definitions
        tool_names = [t.name for t in tools]
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "execute_command" in tool_names
        
        print_result("Mock tool definitions", True, f"Tools: {', '.join(tool_names)}")
        
        return True
        
    except Exception as e:
        print_result("MCP client mock", False, str(e))
        import traceback
        traceback.print_exc()
        return False


async def test_mock_tool_execution():
    """Test mock tool execution."""
    print_header("Test 6: Mock Tool Execution")
    
    try:
        from agents.tool_executor import MockMCPClient
        
        mock_client = MockMCPClient()
        await mock_client.connect_all()
        
        # Test read_file
        result = await mock_client.call_tool("read_file", {"path": "test.py"})
        assert "[Mock file content" in result
        print_result("Mock read_file", True, result[:50])
        
        # Test write_file
        result = await mock_client.call_tool(
            "write_file",
            {"path": "test.py", "content": "print('hello')"}
        )
        assert "Mock" in result
        print_result("Mock write_file", True, result[:50])
        
        # Test execute_command
        result = await mock_client.call_tool(
            "execute_command",
            {"command": "echo hello"}
        )
        assert "Mock" in result
        print_result("Mock execute_command", True, result[:50])
        
        await mock_client.disconnect_all()
        print_result("Mock disconnect", True)
        
        return True
        
    except Exception as e:
        print_result("Mock tool execution", False, str(e))
        import traceback
        traceback.print_exc()
        return False


def test_system_prompts():
    """Test system prompt generation."""
    print_header("Test 7: System Prompts")
    
    try:
        from integration import AutoDevPipeline, CoderPipeline, PipelineConfig
        
        config = PipelineConfig()
        
        # Test default system prompt
        pipeline = AutoDevPipeline(config)
        default_prompt = pipeline._get_default_system_prompt()
        
        assert len(default_prompt) > 100
        assert "tool" in default_prompt.lower()
        
        print_result(
            "Default system prompt",
            True,
            f"{len(default_prompt)} chars"
        )
        
        # Test coder system prompt
        coder_pipeline = CoderPipeline(config)
        coder_prompt = coder_pipeline._get_default_system_prompt()
        
        assert len(coder_prompt) > 100
        assert "code" in coder_prompt.lower() or "developer" in coder_prompt.lower()
        
        print_result(
            "Coder system prompt",
            True,
            f"{len(coder_prompt)} chars"
        )
        
        return True
        
    except Exception as e:
        print_result("System prompts", False, str(e))
        import traceback
        traceback.print_exc()
        return False


def test_execution_result_fields():
    """Test ExecutionResult has all required fields."""
    print_header("Test 8: ExecutionResult Fields")
    
    try:
        from integration import ExecutionResult
        import inspect
        
        # Get dataclass fields
        fields = {f.name: f for f in ExecutionResult.__dataclass_fields__.values()}
        
        required_fields = [
            'success', 'content', 'files_modified', 'tools_called',
            'iterations', 'tokens_used', 'execution_time_seconds',
            'error', 'metadata'
        ]
        
        for field_name in required_fields:
            assert field_name in fields, f"Missing field: {field_name}"
        
        print_result(
            "ExecutionResult fields",
            True,
            f"All {len(required_fields)} fields present"
        )
        
        # Create instance with all fields
        result = ExecutionResult(
            success=True,
            content="Test",
            files_modified=["file1.py"],
            tools_called=[{"name": "test"}],
            iterations=1,
            tokens_used={"total": 100},
            execution_time_seconds=1.5,
            error=None,
            metadata={"key": "value"}
        )
        
        # Verify defaults work
        result2 = ExecutionResult(success=True, content="Test")
        assert result2.files_modified == []
        assert result2.tools_called == []
        
        print_result("ExecutionResult instantiation", True)
        
        return True
        
    except Exception as e:
        print_result("ExecutionResult fields", False, str(e))
        import traceback
        traceback.print_exc()
        return False


def test_pipeline_config_fields():
    """Test PipelineConfig has all required fields."""
    print_header("Test 9: PipelineConfig Fields")
    
    try:
        from integration import PipelineConfig
        
        # Create with defaults
        config = PipelineConfig()
        
        assert config.max_tool_iterations == 20
        assert config.enable_parallel_tools == False
        assert config.workspace_path == "."
        
        print_result(
            "PipelineConfig defaults",
            True,
            f"max_iterations={config.max_tool_iterations}"
        )
        
        # Create with custom values
        config2 = PipelineConfig(
            max_tool_iterations=30,
            enable_parallel_tools=True,
            workspace_path="/custom/path"
        )
        
        assert config2.max_tool_iterations == 30
        assert config2.enable_parallel_tools == True
        assert config2.workspace_path == "/custom/path"
        
        print_result("PipelineConfig customization", True)
        
        return True
        
    except Exception as e:
        print_result("PipelineConfig fields", False, str(e))
        import traceback
        traceback.print_exc()
        return False


async def test_tool_executor_with_mock():
    """Test tool executor with mock MCP client."""
    print_header("Test 10: Tool Executor with Mock")
    
    try:
        from agents.tool_executor import ToolExecutionLoop, MockMCPClient
        from llm.base_client import ChatMessage, MessageRole
        
        # Create mock client
        mock_mcp = MockMCPClient()
        await mock_mcp.connect_all()
        
        # Create mock LLM client that returns a simple response
        class MockLLMClient:
            async def complete(self, **kwargs):
                from llm.base_client import LLMResponse
                return LLMResponse(
                    content="Task completed successfully!",
                    tool_uses=[],
                    stop_reason="end_turn"
                )
        
        mock_llm = MockLLMClient()
        
        # Create tool executor
        executor = ToolExecutionLoop(
            llm_client=mock_llm,
            mcp_client=mock_mcp,
            max_iterations=5
        )
        
        # Execute
        messages = [ChatMessage(
            role=MessageRole.USER,
            content="Test task"
        )]
        
        result = await executor.execute_with_tools(
            initial_messages=messages,
            system_prompt="You are a test assistant."
        )
        
        assert result == "Task completed successfully!"
        
        # Check stats
        stats = executor.get_stats()
        assert stats['iterations'] == 1
        
        print_result(
            "Tool executor with mock",
            True,
            f"Completed in {stats['iterations']} iteration(s)"
        )
        
        await mock_mcp.disconnect_all()
        
        return True
        
    except Exception as e:
        print_result("Tool executor with mock", False, str(e))
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all mock mode tests."""
    print("\n" + "="*60)
    print("  AutoDev Phase 5 Integration Tests (Mock Mode)")
    print("="*60)
    print("\nRunning tests without real API credentials...")
    
    tests = [
        ("Module Imports", test_imports),
        ("Data Structures", test_data_structures),
        ("Pipeline Creation", test_pipeline_creation),
        ("Convenience Functions", test_convenience_functions),
        ("MCP Client Mock", test_mcp_client_mock),
        ("Mock Tool Execution", test_mock_tool_execution),
        ("System Prompts", test_system_prompts),
        ("ExecutionResult Fields", test_execution_result_fields),
        ("PipelineConfig Fields", test_pipeline_config_fields),
        ("Tool Executor with Mock", test_tool_executor_with_mock),
    ]
    
    results = {}
    
    for name, test_func in tests:
        try:
            if asyncio.iscoroutinefunction(test_func):
                results[name] = await test_func()
            else:
                results[name] = test_func()
        except Exception as e:
            print(f"\n❌ Test '{name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results[name] = False
    
    # Print summary
    print_header("Test Summary")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    print(f"Results: {passed}/{total} tests passed\n")
    
    for name, success in results.items():
        status = "✅" if success else "❌"
        print(f"  {status} {name}")
    
    print("\n" + "="*60)
    
    if passed == total:
        print("  🎉 All mock mode tests passed!")
        print("\n  To run with real API, set ANTHROPIC_API_KEY and run:")
        print("  python test_phase5_integration.py")
    else:
        print(f"  ⚠️  {total - passed} test(s) failed")
    
    print("="*60 + "\n")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
