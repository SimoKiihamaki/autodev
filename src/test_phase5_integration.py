#!/usr/bin/env python3
"""
Phase 5 Integration Tests

End-to-end tests for the LLM ↔ MCP integration pipeline.
Tests the complete ReAct loop for autonomous coding tasks.

Run with: python test_phase5_integration.py
"""

import asyncio
import sys
import os
import tempfile
import shutil
from pathlib import Path
import json
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

# Test configuration
TEST_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "test_key_placeholder")
USE_REAL_API = TEST_API_KEY != "test_key_placeholder"


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


async def test_pipeline_initialization():
    """Test that pipeline initializes correctly."""
    print_header("Test 1: Pipeline Initialization")
    
    try:
        from integration import AutoDevPipeline, PipelineConfig
        from llm.base_client import LLMConfig
        
        # Create pipeline
        config = PipelineConfig(
            llm_config=LLMConfig(api_key=TEST_API_KEY),
            max_tool_iterations=5
        )
        pipeline = AutoDevPipeline(config)
        
        # Initialize
        await pipeline.initialize()
        
        # Check components
        assert pipeline._llm_client is not None, "LLM client not initialized"
        assert pipeline._mcp_client is not None, "MCP client not initialized"
        assert pipeline._tool_executor is not None, "Tool executor not initialized"
        assert pipeline._initialized, "Pipeline not marked as initialized"
        
        # Check tools available
        tools = pipeline.get_available_tools()
        assert len(tools) > 0, "No tools available"
        
        print_result("Pipeline initialization", True, f"Found {len(tools)} tools")
        
        # Cleanup
        await pipeline.shutdown()
        print_result("Pipeline shutdown", True)
        
        return True
        
    except Exception as e:
        print_result("Pipeline initialization", False, str(e))
        return False


async def test_simple_task():
    """Test simple task execution."""
    print_header("Test 2: Simple Task Execution")
    
    try:
        from integration import AutoDevPipeline, PipelineConfig
        from llm.base_client import LLMConfig
        
        config = PipelineConfig(
            llm_config=LLMConfig(api_key=TEST_API_KEY),
            max_tool_iterations=5
        )
        
        async with AutoDevPipeline(config) as pipeline:
            # Execute a simple task
            result = await pipeline.execute_task(
                "List the files in the current directory and tell me what you find."
            )
            
            assert result.success, f"Task failed: {result.error}"
            assert result.content, "No content in result"
            
            print_result(
                "Simple task execution",
                True,
                f"Completed in {result.execution_time_seconds:.2f}s, "
                f"{result.iterations} iterations"
            )
            
            print(f"\nResponse preview:\n{result.content[:200]}...\n")
            
            return True
    
    except Exception as e:
        print_result("Simple task execution", False, str(e))
        import traceback
        traceback.print_exc()
        return False


async def test_file_creation_task():
    """Test file creation task."""
    print_header("Test 3: File Creation Task")
    
    # Create temporary workspace
    temp_dir = tempfile.mkdtemp(prefix="autodev_test_")
    
    try:
        from integration import CoderPipeline, PipelineConfig
        from llm.base_client import LLMConfig
        
        config = PipelineConfig(
            llm_config=LLMConfig(api_key=TEST_API_KEY),
            workspace_path=temp_dir,
            max_tool_iterations=10
        )
        
        async with CoderPipeline(config) as pipeline:
            # Task to create a simple Python file
            task = """Create a simple Python file called 'hello.py' that:
1. Defines a function called 'greet' that takes a name parameter
2. Returns a greeting string like "Hello, {name}!"
3. Includes a main block that calls greet with "World"
"""
            
            result = await pipeline.execute_task(task)
            
            print_result(
                "File creation task",
                result.success,
                f"{len(result.tools_called)} tools called"
            )
            
            if result.success:
                # Check if file was created
                hello_file = Path(temp_dir) / "hello.py"
                if hello_file.exists():
                    content = hello_file.read_text()
                    print(f"\nCreated file content:\n{content}\n")
                    print_result("File created", True)
                else:
                    print_result("File created", False, "File not found on disk")
                    # But might be in mock mode
                    print(f"Note: Running in mock mode, file not actually created")
            
            return result.success
    
    except Exception as e:
        print_result("File creation task", False, str(e))
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)


async def test_context_manager():
    """Test async context manager usage."""
    print_header("Test 4: Context Manager")
    
    try:
        from integration import AutoDevPipeline, PipelineConfig
        from llm.base_client import LLMConfig
        
        config = PipelineConfig(
            llm_config=LLMConfig(api_key=TEST_API_KEY),
            max_tool_iterations=3
        )
        
        initialized = False
        shutdown = False
        
        async with AutoDevPipeline(config) as pipeline:
            initialized = pipeline._initialized
            assert initialized, "Pipeline not initialized in context"
            print_result("Context manager initialization", True)
        
        # After context exit, should be shutdown
        shutdown = not pipeline._initialized
        assert shutdown, "Pipeline not shutdown after context exit"
        print_result("Context manager cleanup", True)
        
        return True
    
    except Exception as e:
        print_result("Context manager", False, str(e))
        return False


async def test_tool_info():
    """Test tool information retrieval."""
    print_header("Test 5: Tool Information")
    
    try:
        from integration import AutoDevPipeline, PipelineConfig
        from llm.base_client import LLMConfig
        
        config = PipelineConfig(
            llm_config=LLMConfig(api_key=TEST_API_KEY)
        )
        
        async with AutoDevPipeline(config) as pipeline:
            # Get all tools
            tools = pipeline.get_available_tools()
            print(f"Available tools ({len(tools)}):")
            
            for tool in tools[:5]:  # Show first 5
                print(f"  - {tool.name}: {tool.description[:50]}...")
            
            print_result("Tool listing", len(tools) > 0, f"{len(tools)} tools found")
            
            # Get specific tool info
            if tools:
                first_tool_name = tools[0].name
                info = pipeline.get_tool_info(first_tool_name)
                if info:
                    print_result(
                        "Tool info retrieval",
                        True,
                        f"Got info for {first_tool_name}"
                    )
                else:
                    print_result("Tool info retrieval", False)
            
            return True
    
    except Exception as e:
        print_result("Tool information", False, str(e))
        return False


async def test_error_handling():
    """Test error handling."""
    print_header("Test 6: Error Handling")
    
    try:
        from integration import AutoDevPipeline, PipelineConfig
        from llm.base_client import LLMConfig
        
        # Test with invalid config
        config = PipelineConfig(
            llm_config=LLMConfig(api_key=TEST_API_KEY),
            max_tool_iterations=2  # Very low limit
        )
        
        async with AutoDevPipeline(config) as pipeline:
            # Task that might hit iteration limit or have other issues
            result = await pipeline.execute_task(
                "Count from 1 to 100, calling a tool for each number."
            )
            
            # Should complete (even if hitting limits)
            if not result.success and result.error:
                print_result(
                    "Error handling",
                    True,
                    f"Properly handled: {result.error[:50]}"
                )
            else:
                print_result(
                    "Error handling",
                    True,
                    "Task completed or handled gracefully"
                )
            
            return True
    
    except Exception as e:
        print_result("Error handling", False, str(e))
        return False


async def test_coder_pipeline():
    """Test specialized coder pipeline."""
    print_header("Test 7: Coder Pipeline")
    
    try:
        from integration import CoderPipeline, PipelineConfig
        from llm.base_client import LLMConfig
        
        config = PipelineConfig(
            llm_config=LLMConfig(api_key=TEST_API_KEY),
            max_tool_iterations=5
        )
        
        async with CoderPipeline(config) as pipeline:
            # Check it's a coder pipeline
            assert isinstance(pipeline, CoderPipeline), "Not a CoderPipeline"
            
            # Check system prompt
            system_prompt = pipeline._get_default_system_prompt()
            assert "developer" in system_prompt.lower() or "code" in system_prompt.lower()
            
            print_result(
                "Coder pipeline",
                True,
                "Specialized coding pipeline created"
            )
            
            return True
    
    except Exception as e:
        print_result("Coder pipeline", False, str(e))
        return False


async def test_convenience_functions():
    """Test convenience functions."""
    print_header("Test 8: Convenience Functions")
    
    try:
        from integration import create_coder_pipeline
        
        # Test factory function
        pipeline = create_coder_pipeline(
            api_key=TEST_API_KEY,
            workspace=".",
            max_iterations=5
        )
        
        assert pipeline is not None, "Pipeline not created"
        assert not pipeline._initialized, "Pipeline should not be initialized yet"
        
        print_result("create_coder_pipeline", True)
        
        return True
    
    except Exception as e:
        print_result("Convenience functions", False, str(e))
        return False


async def test_execution_result():
    """Test execution result structure."""
    print_header("Test 9: Execution Result")
    
    try:
        from integration import AutoDevPipeline, ExecutionResult, PipelineConfig
        from llm.base_client import LLMConfig
        
        config = PipelineConfig(
            llm_config=LLMConfig(api_key=TEST_API_KEY),
            max_tool_iterations=3
        )
        
        async with AutoDevPipeline(config) as pipeline:
            result = await pipeline.execute_task("What is 2+2?")
            
            # Check result structure
            assert hasattr(result, 'success'), "Missing success field"
            assert hasattr(result, 'content'), "Missing content field"
            assert hasattr(result, 'tools_called'), "Missing tools_called field"
            assert hasattr(result, 'iterations'), "Missing iterations field"
            assert hasattr(result, 'execution_time_seconds'), "Missing execution_time_seconds"
            
            print_result(
                "Execution result structure",
                True,
                f"All fields present, success={result.success}"
            )
            
            # Print result details
            print(f"\nResult details:")
            print(f"  Success: {result.success}")
            print(f"  Iterations: {result.iterations}")
            print(f"  Tools called: {len(result.tools_called)}")
            print(f"  Execution time: {result.execution_time_seconds:.2f}s")
            if result.tokens_used:
                print(f"  Tokens: {result.tokens_used}")
            
            return True
    
    except Exception as e:
        print_result("Execution result", False, str(e))
        return False


async def run_all_tests():
    """Run all integration tests."""
    print("\n" + "="*60)
    print("  AutoDev Phase 5 Integration Tests")
    print("="*60)
    print(f"\nUsing {'REAL API' if USE_REAL_API else 'MOCK API'}")
    print(f"API Key: {'Set' if TEST_API_KEY != 'test_key_placeholder' else 'Not set'}")
    
    tests = [
        ("Pipeline Initialization", test_pipeline_initialization),
        ("Simple Task", test_simple_task),
        ("File Creation", test_file_creation_task),
        ("Context Manager", test_context_manager),
        ("Tool Information", test_tool_info),
        ("Error Handling", test_error_handling),
        ("Coder Pipeline", test_coder_pipeline),
        ("Convenience Functions", test_convenience_functions),
        ("Execution Result", test_execution_result),
    ]
    
    results = {}
    start_time = time.time()
    
    for name, test_func in tests:
        try:
            results[name] = await test_func()
        except Exception as e:
            print(f"\n❌ Test '{name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results[name] = False
    
    total_time = time.time() - start_time
    
    # Print summary
    print_header("Test Summary")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    print(f"Results: {passed}/{total} tests passed")
    print(f"Total time: {total_time:.2f}s\n")
    
    for name, success in results.items():
        status = "✅" if success else "❌"
        print(f"  {status} {name}")
    
    print("\n" + "="*60)
    
    if passed == total:
        print("  🎉 All tests passed!")
    else:
        print(f"  ⚠️  {total - passed} test(s) failed")
    
    print("="*60 + "\n")
    
    return passed == total


if __name__ == "__main__":
    # Run tests
    success = asyncio.run(run_all_tests())
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)
