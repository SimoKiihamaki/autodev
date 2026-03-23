#!/usr/bin/env python3
"""
AutoDev Phase 5 End-to-End Demo

Demonstrates the complete LLM ↔ MCP integration for autonomous coding.

This demo:
1. Initializes the pipeline
2. Shows available tools
3. Executes a simple task
4. Displays results and statistics

Run: python demo_integration.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("="*70)
print("  AutoDev Phase 5: LLM ↔ MCP Integration Demo")
print("="*70)


async def demo():
    """Run the demo."""
    
    # 1. Check API key
    print("\n[1] Checking configuration...")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    
    if not api_key:
        print("    ⚠️  ANTHROPIC_API_KEY not set")
        print("    → Running in mock mode (no real LLM calls)")
        api_key = "mock-key-for-demo"
        mock_mode = True
    else:
        print(f"    ✓ API key found: {api_key[:10]}...")
        mock_mode = False
    
    # 2. Import and configure
    print("\n[2] Loading integration layer...")
    try:
        from integration import AutoDevPipeline, PipelineConfig
        from llm.base_client import LLMConfig
        print("    ✓ Integration module loaded")
    except Exception as e:
        print(f"    ❌ Failed to load: {e}")
        return False
    
    # 3. Create pipeline configuration
    print("\n[3] Creating pipeline configuration...")
    config = PipelineConfig(
        llm_config=LLMConfig(
            api_key=api_key,
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            temperature=0.7
        ),
        max_tool_iterations=5,
        workspace_path=".",
        enable_logging=False  # Quiet for demo
    )
    print(f"    ✓ Max iterations: {config.max_tool_iterations}")
    print(f"    ✓ Workspace: {config.workspace_path}")
    
    # 4. Initialize pipeline
    print("\n[4] Initializing pipeline...")
    pipeline = AutoDevPipeline(config)
    
    try:
        await pipeline.initialize()
        print("    ✓ Pipeline initialized")
    except Exception as e:
        print(f"    ⚠️  Initialization note: {e}")
        if "anthropic package not installed" in str(e):
            print("    → Continuing with mock components...")
            # Create mock components manually
            from agents.tool_executor import MockMCPClient
            pipeline._mcp_client = MockMCPClient()
            await pipeline._mcp_client.connect_all()
            pipeline._initialized = True
        else:
            return False
    
    # 5. Show available tools
    print("\n[5] Available MCP tools...")
    tools = pipeline.get_available_tools()
    if tools:
        print(f"    Found {len(tools)} tools:")
        for i, tool in enumerate(tools[:8], 1):
            print(f"      {i}. {tool.name}: {tool.description[:40]}...")
    else:
        print("    No tools discovered (running in limited mode)")
    
    # 6. Execute a task
    print("\n[6] Executing sample task...")
    task = "List the files in the current directory and briefly describe what you find."
    print(f"    Task: '{task[:60]}...'")
    
    try:
        result = await pipeline.execute_task(task)
        
        # 7. Display results
        print("\n[7] Results")
        print("    " + "-"*60)
        print(f"    Success: {result.success}")
        print(f"    Iterations: {result.iterations}")
        print(f"    Tools called: {len(result.tools_called)}")
        print(f"    Execution time: {result.execution_time_seconds:.2f}s")
        
        if result.tools_called:
            print("\n    Tool calls:")
            for tc in result.tools_called:
                print(f"      - {tc.get('name', 'unknown')}")
        
        print("\n    Response:")
        print("    " + "-"*60)
        # Print response with indentation
        for line in result.content[:500].split('\n'):
            print(f"    {line}")
        if len(result.content) > 500:
            print("    ...")
        
    except Exception as e:
        print(f"    ❌ Task execution failed: {e}")
        # Try simpler approach with mock
        print("\n    → Trying mock mode execution...")
        try:
            from agents.tool_executor import MockMCPClient, ToolExecutionLoop
            from llm.base_client import ChatMessage, MessageRole, LLMResponse
            
            class SimpleMockLLM:
                async def complete(self, **kwargs):
                    return LLMResponse(
                        content="I found several files in the directory including Python source files for the AutoDev project integration layer.",
                        tool_uses=[],
                        stop_reason="end_turn"
                    )
            
            mock_llm = SimpleMockLLM()
            mock_mcp = MockMCPClient()
            await mock_mcp.connect_all()
            
            executor = ToolExecutionLoop(mock_llm, mock_mcp, max_iterations=3)
            result = await executor.execute_with_tools(
                initial_messages=[ChatMessage(role=MessageRole.USER, content=task)],
                system_prompt="You are a helpful assistant."
            )
            
            print(f"\n    Mock result: {result}")
            
        except Exception as e2:
            print(f"    ❌ Mock mode also failed: {e2}")
    
    # 8. Cleanup
    print("\n[8] Cleanup...")
    try:
        await pipeline.shutdown()
        print("    ✓ Pipeline shutdown complete")
    except Exception as e:
        print(f"    Note: {e}")
    
    print("\n" + "="*70)
    print("  Demo Complete!")
    print("="*70)
    
    if mock_mode:
        print("\n  ℹ️  Run with ANTHROPIC_API_KEY for full functionality:")
        print("     export ANTHROPIC_API_KEY='your-key'")
        print("     python demo_integration.py")
    
    return True


if __name__ == "__main__":
    success = asyncio.run(demo())
    sys.exit(0 if success else 1)
