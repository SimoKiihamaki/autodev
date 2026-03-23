#!/usr/bin/env python3
"""
Quick verification script for Phase 4 MCP Client.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Test imports
print("Testing imports...")
try:
    from mcp import (
        AutoDevMCPClient,
        MCPServerConfig,
        MCPSecurityConfig,
        MCPToolInfo,
        MCPResourceInfo,
        MCPPromptInfo,
        MCPServerHealth,
        MCPMetrics,
        ServerStatus,
        MCPConnectionError,
        MCPToolError,
        MCPSecurityError,
        MCPResourceError,
        MCP_AVAILABLE,
    )
    print("✓ All imports successful")
except ImportError as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)

# Test data classes
print("\nTesting data classes...")
try:
    # Server config
    config = MCPServerConfig(name="test", command="test-cmd", args=["--arg"])
    assert config.name == "test"
    print("✓ MCPServerConfig works")
    
    # Security config
    security = MCPSecurityConfig(allowed_paths=["/tmp"], allow_all_commands=True)
    assert security.is_path_allowed("/tmp") is True
    assert security.is_path_allowed("/etc") is False
    print("✓ MCPSecurityConfig works")
    
    # Metrics
    metrics = MCPMetrics()
    metrics.record_tool_call(True, 100.0)
    assert metrics.total_tool_calls == 1
    print("✓ MCPMetrics works")
    
    # Server health
    health = MCPServerHealth(
        server_name="test",
        status=ServerStatus.CONNECTED,
        last_check=None
    )
    assert health.status == ServerStatus.CONNECTED
    print("✓ MCPServerHealth works")
    
except Exception as e:
    print(f"✗ Data class test failed: {e}")
    sys.exit(1)

# Test async client
print("\nTesting AutoDevMCPClient...")
try:
    import asyncio
    
    async def test_client():
        security = MCPSecurityConfig(allow_all_paths=True, allow_all_commands=True)
        client = AutoDevMCPClient(security_config=security)
        
        # Test add/remove server
        client.add_server(MCPServerConfig(name="test1", command="cmd1"))
        client.add_server(MCPServerConfig(name="test2", command="cmd2"))
        assert len(client.servers) == 2
        print("✓ add_server works")
        
        client.remove_server("test2")
        assert len(client.servers) == 1
        print("✓ remove_server works")
        
        # Connect
        await client.connect_all()
        assert client._initialized is True
        print("✓ connect_all works")
        
        # List tools
        tools = client.list_tools()
        assert len(tools) > 0
        print(f"✓ list_tools returns {len(tools)} tools")
        
        # Get tools for LLM
        llm_tools = client.get_tools_for_llm()
        assert len(llm_tools) > 0
        print(f"✓ get_tools_for_llm returns {len(llm_tools)} tools")
        
        # Call a tool
        result = await client.call_tool("read_file", {"path": "/tmp/test"}, bypass_security=True)
        print(f"✓ call_tool works: {result[:50]}...")
        
        # List resources
        resources = await client.list_resources()
        print(f"✓ list_resources returns {len(resources)} resources")
        
        # List prompts
        prompts = await client.list_prompts()
        print(f"✓ list_prompts returns {len(prompts)} prompts")
        
        # Health check
        health = await client.health_check()
        print(f"✓ health_check returns {len(health)} server statuses")
        
        # Metrics
        summary = client.get_metrics_summary()
        print(f"✓ get_metrics_summary: {summary}")
        
        # Full status
        status = client.get_full_status()
        assert status["initialized"] is True
        print("✓ get_full_status works")
        
        # Disconnect
        await client.disconnect_all()
        assert client._initialized is False
        print("✓ disconnect_all works")
        
        # Test context manager
        async with AutoDevMCPClient(security_config=security) as client2:
            assert client2._initialized is True
        assert client2._initialized is False
        print("✓ Context manager works")
    
    asyncio.run(test_client())
    
except Exception as e:
    import traceback
    print(f"✗ Client test failed: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*50)
print("All Phase 4 MCP Client tests passed!")
print("="*50)
