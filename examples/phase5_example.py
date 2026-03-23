#!/usr/bin/env python3
"""
AutoDev Phase 5 Integration Example

This example demonstrates how to use the LLM ↔ MCP integration
to create a complete autonomous coding pipeline.

Usage:
    # Set API key
    export ANTHROPIC_API_KEY="your-key"
    
    # Run example
    python phase5_example.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def basic_example():
    """Basic usage example."""
    print("="*60)
    print("  Example 1: Basic Pipeline Usage")
    print("="*60)
    
    from integration import AutoDevPipeline, PipelineConfig
    from llm.base_client import LLMConfig
    
    # Configure the pipeline
    config = PipelineConfig(
        llm_config=LLMConfig(
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
            model="claude-3-5-sonnet-20241022"
        ),
        max_tool_iterations=10,
        workspace_path="."
    )
    
    # Use context manager for automatic cleanup
    async with AutoDevPipeline(config) as pipeline:
        # Execute a simple task
        result = await pipeline.execute_task(
            "List the files in the current directory and briefly describe what you see."
        )
        
        print(f"\n✓ Success: {result.success}")
        print(f"✓ Iterations: {result.iterations}")
        print(f"✓ Tools called: {len(result.tools_called)}")
        print(f"✓ Execution time: {result.execution_time_seconds:.2f}s")
        print(f"\nResponse:\n{result.content[:500]}...")


async def coder_pipeline_example():
    """Coder pipeline example."""
    print("\n" + "="*60)
    print("  Example 2: Coder Pipeline")
    print("="*60)
    
    from integration import CoderPipeline, PipelineConfig
    from llm.base_client import LLMConfig
    
    config = PipelineConfig(
        llm_config=LLMConfig(
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
            model="claude-3-5-sonnet-20241022"
        ),
        max_tool_iterations=15
    )
    
    async with CoderPipeline(config) as pipeline:
        # Get available tools
        tools = pipeline.get_available_tools()
        print(f"\nAvailable tools ({len(tools)}):")
        for tool in tools[:5]:
            print(f"  - {tool.name}: {tool.description[:50]}...")
        
        # Execute a coding task
        result = await pipeline.execute_task(
            "Explain what files are in this directory and what the project appears to be."
        )
        
        print(f"\n✓ Task completed: {result.success}")
        print(f"\nAnalysis:\n{result.content[:500]}...")


async def with_callbacks_example():
    """Example with tool call callbacks."""
    print("\n" + "="*60)
    print("  Example 3: With Callbacks")
    print("="*60)
    
    from integration import AutoDevPipeline, PipelineConfig
    from llm.base_client import LLMConfig
    
    # Callbacks
    def on_tool_call(tool_name: str, tool_input: dict):
        print(f"  → Tool called: {tool_name}")
        if tool_input:
            print(f"     Input: {str(tool_input)[:100]}...")
    
    def on_iteration(iteration: int, response):
        print(f"  🔄 Iteration {iteration}: {response.stop_reason}")
    
    config = PipelineConfig(
        llm_config=LLMConfig(
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
        ),
        max_tool_iterations=5
    )
    
    async with AutoDevPipeline(config) as pipeline:
        result = await pipeline.execute_task(
            "What is in this directory?",
            on_tool_call=on_tool_call,
            on_iteration=on_iteration
        )
        
        print(f"\n✓ Completed in {result.iterations} iterations")
        print(f"✓ Total tools called: {len(result.tools_called)}")


async def quick_code_example():
    """Quick code convenience function example."""
    print("\n" + "="*60)
    print("  Example 4: Quick Code Function")
    print("="*60)
    
    from integration import quick_code
    
    # One-liner for quick tasks
    result = await quick_code(
        "What is 2 + 2? Just give me the number.",
        api_key=os.environ.get("ANTHROPIC_API_KEY")
    )
    
    print(f"\nResult: {result}")


async def mock_mode_example():
    """Example running in mock mode (no API key needed)."""
    print("\n" + "="*60)
    print("  Example 5: Mock Mode (No API Key)")
    print("="*60)
    
    from integration import AutoDevPipeline, PipelineConfig
    from llm.base_client import LLMConfig
    
    config = PipelineConfig(
        llm_config=LLMConfig(api_key="mock-key"),  # Will use mock
        max_tool_iterations=5
    )
    
    # Check available tools without initialization
    pipeline = AutoDevPipeline(config)
    
    print("\nThis example shows the pipeline structure.")
    print("In mock mode, the MCP client provides simulated tool responses.")
    
    # Show what tools would be available
    from agents.tool_executor import MockMCPClient
    mock = MockMCPClient()
    tools = mock.get_tools_for_llm()
    
    print(f"\nMock tools available: {len(tools)}")
    for tool in tools:
        print(f"  - {tool.name}")


def print_usage():
    """Print usage information."""
    print("""
AutoDev Phase 5 Integration Examples

These examples demonstrate the LLM ↔ MCP integration for autonomous coding.

Setup:
    export ANTHROPIC_API_KEY="your-anthropic-api-key"

Examples:
    1. Basic Pipeline    - Simple task execution
    2. Coder Pipeline    - Specialized coding pipeline
    3. With Callbacks    - Monitor tool calls and iterations
    4. Quick Code        - One-liner convenience function
    5. Mock Mode         - Run without API key

To run all examples:
    python phase5_example.py

Note: Examples 1-4 require ANTHROPIC_API_KEY.
Example 5 runs in mock mode without a real API key.
""")


async def main():
    """Run examples."""
    print_usage()
    
    # Check if API key is available
    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    
    if not has_api_key:
        print("\n⚠️  No ANTHROPIC_API_KEY found.")
        print("Running only mock mode example...\n")
        await mock_mode_example()
        print("\n✓ Mock mode example completed.")
        print("\nTo run all examples, set ANTHROPIC_API_KEY:")
        print("  export ANTHROPIC_API_KEY='your-key'")
        return
    
    # Run all examples
    try:
        await basic_example()
    except Exception as e:
        print(f"❌ Basic example failed: {e}")
    
    try:
        await coder_pipeline_example()
    except Exception as e:
        print(f"❌ Coder pipeline example failed: {e}")
    
    try:
        await with_callbacks_example()
    except Exception as e:
        print(f"❌ Callbacks example failed: {e}")
    
    try:
        await quick_code_example()
    except Exception as e:
        print(f"❌ Quick code example failed: {e}")
    
    try:
        await mock_mode_example()
    except Exception as e:
        print(f"❌ Mock mode example failed: {e}")
    
    print("\n" + "="*60)
    print("  All examples completed!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
