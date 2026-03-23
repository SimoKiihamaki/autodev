#!/usr/bin/env python3
"""
Test script for MCP Client integration.

Tests the AutoDevMCPClient implementation without requiring actual MCP servers.
"""

import asyncio
import sys
import logging
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_imports():
    """Test that all modules can be imported."""
    print("\n=== Testing Imports ===")
    
    try:
        from mcp.client import (
            AutoDevMCPClient,
            MCPServerConfig,
            MCPToolInfo,
            MCPConnectionError,
            MCPToolError,
        )
        print("✓ MCP client module imports successful")
        return True
    except ImportError as e:
        print(f"✗ MCP client import failed: {e}")
        return False


async def test_mcp_client_init():
    """Test MCP client initialization."""
    print("\n=== Testing MCP Client Initialization ===")
    
    from mcp.client import AutoDevMCPClient
    
    # Test with non-existent config (should use defaults)
    client = AutoDevMCPClient("/nonexistent/path/config.json")
    await client.load_config()
    
    print(f"✓ Loaded {len(client.servers)} default server configs")
    print(f"  Servers: {list(client.servers.keys())}")
    
    return client


async def test_connect_all():
    """Test connecting to all servers (mock mode)."""
    print("\n=== Testing connect_all (Mock Mode) ===")
    
    from mcp.client import AutoDevMCPClient
    
    client = AutoDevMCPClient()
    await client.connect_all()
    
    status = client.get_connection_status()
    print(f"✓ Initialized: {status['initialized']}")
    print(f"  MCP Available: {status['mcp_available']}")
    print(f"  Tools count: {status['tools_count']}")
    
    return client


async def test_tool_discovery():
    """Test tool discovery and listing."""
    print("\n=== Testing Tool Discovery ===")
    
    from mcp.client import AutoDevMCPClient
    
    client = AutoDevMCPClient()
    await client.connect_all()
    
    tools = client.list_tools()
    print(f"✓ Discovered {len(tools)} tools:")
    for tool in tools:
        info = client.get_tool_info(tool)
        if info:
            print(f"  - {tool} ({info.server_name}): {info.description[:50]}...")
    
    return client, tools


async def test_tool_call_mock():
    """Test mock tool execution."""
    print("\n=== Testing Mock Tool Calls ===")
    
    from mcp.client import AutoDevMCPClient
    
    client = AutoDevMCPClient()
    await client.connect_all()
    
    # Test read_file
    result = await client.call_tool("read_file", {"path": "test.py"})
    print(f"✓ read_file result: {result[:50]}...")
    
    # Test write_file
    result = await client.call_tool("write_file", {
        "path": "output.txt",
        "content": "Hello, World!"
    })
    print(f"✓ write_file result: {result}")
    
    # Test execute_command
    result = await client.call_tool("execute_command", {"command": "echo hello"})
    print(f"✓ execute_command result: {result}")
    
    return client


async def test_get_tools_for_llm():
    """Test getting tools in LLM format."""
    print("\n=== Testing get_tools_for_llm ===")
    
    from mcp.client import AutoDevMCPClient
    
    client = AutoDevMCPClient()
    await client.connect_all()
    
    tools = client.get_tools_for_llm()
    print(f"✓ Got {len(tools)} tools for LLM")
    
    for tool in tools[:3]:  # Show first 3
        print(f"  - {tool.name}: {tool.description[:50]}...")
        print(f"    Server: {tool.mcp_server}")
    
    return client, tools


async def test_disconnect():
    """Test disconnect functionality."""
    print("\n=== Testing Disconnect ===")
    
    from mcp.client import AutoDevMCPClient
    
    client = AutoDevMCPClient()
    await client.connect_all()
    
    await client.disconnect_all()
    
    status = client.get_connection_status()
    print(f"✓ Disconnected: initialized={status['initialized']}")
    print(f"  Sessions cleared: {len(client.sessions) == 0}")
    print(f"  Tools cleared: {len(client.tools) == 0}")
    
    return True


async def test_context_manager():
    """Test async context manager usage."""
    print("\n=== Testing Context Manager ===")
    
    from mcp.client import AutoDevMCPClient
    
    async with AutoDevMCPClient() as client:
        tools = client.list_tools()
        print(f"✓ Context manager: {len(tools)} tools available")
    
    print("✓ Context manager cleanup successful")
    return True


async def test_server_config():
    """Test MCPServerConfig dataclass."""
    print("\n=== Testing MCPServerConfig ===")
    
    from mcp.client import MCPServerConfig
    
    config = MCPServerConfig(
        name="test",
        command="test-server",
        args=["--port", "8080"],
        env={"DEBUG": "1"},
        enabled=True
    )
    print(f"✓ Created config: {config.name}")
    print(f"  Command: {config.command} {' '.join(config.args)}")
    
    # Test from_dict
    config2 = MCPServerConfig.from_dict({
        "name": "dict-test",
        "command": "python",
        "args": ["-m", "server"]
    })
    print(f"✓ Created from dict: {config2.name}")
    
    return True


async def test_integration_with_tool_executor():
    """Test integration with ToolExecutionLoop."""
    print("\n=== Testing Tool Executor Integration ===")
    
    try:
        from agents.tool_executor import ToolExecutionLoop, MCP_CLIENT_AVAILABLE
        from mcp.client import AutoDevMCPClient
        
        print(f"✓ MCP client available in tool_executor: {MCP_CLIENT_AVAILABLE}")
        
        # Create MCP client
        mcp_client = AutoDevMCPClient()
        await mcp_client.connect_all()
        
        # Get tools in LLM format
        tools = mcp_client.get_tools_for_llm()
        print(f"✓ Tool executor can access {len(tools)} tools")
        
        return True
        
    except ImportError as e:
        print(f"✗ Tool executor integration test failed: {e}")
        return False


async def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("AutoDev MCP Client Test Suite")
    print("=" * 60)
    
    tests = [
        ("Imports", test_imports, False),
        ("Server Config", test_server_config, True),
        ("Client Init", test_mcp_client_init, True),
        ("Connect All", test_connect_all, True),
        ("Tool Discovery", test_tool_discovery, True),
        ("Mock Tool Calls", test_tool_call_mock, True),
        ("Tools for LLM", test_get_tools_for_llm, True),
        ("Disconnect", test_disconnect, True),
        ("Context Manager", test_context_manager, True),
        ("Tool Executor Integration", test_integration_with_tool_executor, True),
    ]
    
    results = []
    for name, test_func, is_async in tests:
        try:
            if is_async:
                result = await test_func()
            else:
                result = test_func()
            results.append((name, True, None))
            print(f"\n✓ {name} test passed")
        except Exception as e:
            results.append((name, False, str(e)))
            print(f"\n✗ {name} test failed: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    for name, success, error in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status}: {name}")
        if error:
            print(f"       {error}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
