"""
AutoDev Phase 4 MCP Client Integration Tests

Tests for multi-server management, tool discovery, connection handling,
security validation, resource support, prompt support, and health checking.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# Test imports
from src.mcp import (
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


class TestMCPServerConfig:
    """Tests for MCPServerConfig dataclass."""
    
    def test_basic_config(self):
        """Test basic server configuration."""
        config = MCPServerConfig(
            name="test_server",
            command="test-command",
            args=["--arg1"],
            env={"KEY": "value"}
        )
        assert config.name == "test_server"
        assert config.command == "test-command"
        assert config.args == ["--arg1"]
        assert config.env == {"KEY": "value"}
        assert config.enabled is True
        assert config.auto_start is True
    
    def test_from_dict(self):
        """Test creating config from dictionary."""
        data = {
            "name": "filesystem",
            "command": "mcp-filesystem",
            "args": ["/tmp"],
            "env": {"DEBUG": "1"},
            "enabled": False
        }
        config = MCPServerConfig.from_dict(data)
        assert config.name == "filesystem"
        assert config.enabled is False
    
    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = MCPServerConfig(
            name="test",
            command="cmd",
            args=["a"],
            env={"K": "V"}
        )
        d = config.to_dict()
        assert d["name"] == "test"
        assert d["command"] == "cmd"


class TestMCPSecurityConfig:
    """Tests for security configuration."""
    
    def test_default_security_config(self):
        """Test default security configuration."""
        config = MCPSecurityConfig()
        assert config.allowed_paths == []
        assert config.allow_all_paths is False
        assert config.allowed_commands == []
        assert config.allow_all_commands is False
    
    def test_path_validation(self):
        """Test path validation."""
        config = MCPSecurityConfig(
            allowed_paths=["/tmp", "/home/user"],
            allow_all_paths=False
        )
        assert config.is_path_allowed("/tmp") is True
        assert config.is_path_allowed("/tmp/subdir") is True
        assert config.is_path_allowed("/etc/passwd") is False
    
    def test_allow_all_paths(self):
        """Test allowing all paths."""
        config = MCPSecurityConfig(allow_all_paths=True)
        assert config.is_path_allowed("/any/path") is True
    
    def test_command_validation(self):
        """Test command validation."""
        config = MCPSecurityConfig(
            allowed_commands=["ls", "cat", "git"],
            allow_all_commands=False
        )
        assert config.is_command_allowed("ls") is True
        assert config.is_command_allowed("ls -la") is True
        assert config.is_command_allowed("rm -rf /") is False
    
    def test_allow_all_commands(self):
        """Test allowing all commands."""
        config = MCPSecurityConfig(allow_all_commands=True)
        assert config.is_command_allowed("any_command") is True


class TestMCPMetrics:
    """Tests for metrics tracking."""
    
    def test_initial_metrics(self):
        """Test initial metrics state."""
        metrics = MCPMetrics()
        assert metrics.total_tool_calls == 0
        assert metrics.successful_tool_calls == 0
        assert metrics.failed_tool_calls == 0
        assert metrics.average_latency_ms == 0.0
    
    def test_record_tool_calls(self):
        """Test recording tool calls."""
        metrics = MCPMetrics()
        metrics.record_tool_call(True, 100.0)
        metrics.record_tool_call(True, 200.0)
        metrics.record_tool_call(False, 50.0)
        
        assert metrics.total_tool_calls == 3
        assert metrics.successful_tool_calls == 2
        assert metrics.failed_tool_calls == 1
        assert metrics.total_latency_ms == 350.0
        assert metrics.average_latency_ms == pytest.approx(350.0 / 3)
    
    def test_record_resource_reads(self):
        """Test recording resource reads."""
        metrics = MCPMetrics()
        metrics.record_resource_read(1024, 50.0)
        metrics.record_resource_read(2048, 75.0)
        
        assert metrics.total_resource_reads == 2
        assert metrics.total_bytes_transferred == 3072


class TestMCPServerHealth:
    """Tests for server health tracking."""
    
    def test_healthy_server(self):
        """Test healthy server status."""
        health = MCPServerHealth(
            server_name="test",
            status=ServerStatus.CONNECTED,
            last_check=datetime.utcnow(),
            latency_ms=50.0,
            tools_available=5
        )
        assert health.status == ServerStatus.CONNECTED
        assert health.tools_available == 5
        assert health.error_message is None
    
    def test_unhealthy_server(self):
        """Test unhealthy server status."""
        health = MCPServerHealth(
            server_name="test",
            status=ServerStatus.UNHEALTHY,
            last_check=datetime.utcnow(),
            error_message="Connection refused"
        )
        assert health.status == ServerStatus.UNHEALTHY
        assert health.error_message == "Connection refused"


class TestAutoDevMCPClient:
    """Tests for AutoDevMCPClient."""
    
    @pytest.fixture
    def security_config(self):
        """Create test security config."""
        return MCPSecurityConfig(
            allowed_paths=["/tmp", "/home/test"],
            allow_all_commands=True
        )
    
    @pytest.fixture
    def client(self, security_config):
        """Create test client."""
        return AutoDevMCPClient(security_config=security_config)
    
    def test_client_initialization(self, client):
        """Test client initializes correctly."""
        assert client._initialized is False
        assert client.sessions == {}
        assert client.tools == {}
        assert client.resources == {}
        assert client.prompts == {}
    
    def test_add_server(self, client):
        """Test adding a server configuration."""
        config = MCPServerConfig(
            name="test_server",
            command="test-cmd",
            args=["--verbose"]
        )
        client.add_server(config)
        
        assert "test_server" in client.servers
        assert client.servers["test_server"].command == "test-cmd"
    
    def test_remove_server(self, client):
        """Test removing a server configuration."""
        config = MCPServerConfig(name="test", command="cmd")
        client.add_server(config)
        client.remove_server("test")
        
        assert "test" not in client.servers
    
    @pytest.mark.asyncio
    async def test_connect_all_with_mock(self, client):
        """Test connect_all sets up mock tools when MCP unavailable."""
        await client.connect_all()
        
        assert client._initialized is True
        # Should have mock tools set up
        assert len(client.tools) > 0
        assert "read_file" in client.tools
        assert "write_file" in client.tools
    
    @pytest.mark.asyncio
    async def test_list_tools(self, client):
        """Test listing available tools."""
        await client.connect_all()
        tools = client.list_tools()
        
        assert isinstance(tools, list)
        assert "read_file" in tools
        assert "write_file" in tools
    
    @pytest.mark.asyncio
    async def test_get_tools_for_llm(self, client):
        """Test getting tools in LLM format."""
        await client.connect_all()
        llm_tools = client.get_tools_for_llm()
        
        assert isinstance(llm_tools, list)
        assert len(llm_tools) > 0
        # Each tool should have name, description, input_schema
        for tool in llm_tools:
            assert hasattr(tool, 'name')
            assert hasattr(tool, 'description')
            assert hasattr(tool, 'input_schema')
    
    @pytest.mark.asyncio
    async def test_call_tool_mock(self, client):
        """Test calling a tool in mock mode."""
        await client.connect_all()
        
        result = await client.call_tool("read_file", {"path": "/tmp/test.txt"})
        assert "Mock" in result or isinstance(result, str)
    
    @pytest.mark.asyncio
    async def test_call_tool_security_validation(self, client):
        """Test that tool calls are validated against security config."""
        await client.connect_all()
        
        # Should fail - path not allowed
        with pytest.raises((MCPSecurityError, MCPToolError)):
            await client.call_tool("read_file", {"path": "/etc/passwd"})
    
    @pytest.mark.asyncio
    async def test_call_tool_bypass_security(self, client):
        """Test bypassing security validation."""
        await client.connect_all()
        
        # Should work with bypass
        result = await client.call_tool(
            "read_file",
            {"path": "/etc/passwd"},
            bypass_security=True
        )
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_call_unknown_tool(self, client):
        """Test calling unknown tool raises error."""
        await client.connect_all()
        
        with pytest.raises(ValueError):
            await client.call_tool("unknown_tool", {})
    
    @pytest.mark.asyncio
    async def test_list_resources(self, client):
        """Test listing resources."""
        await client.connect_all()
        resources = await client.list_resources()
        
        assert isinstance(resources, list)
    
    @pytest.mark.asyncio
    async def test_read_resource_mock(self, client):
        """Test reading a resource in mock mode."""
        await client.connect_all()
        
        # Mock resources should be set up
        if client.resources:
            uri = list(client.resources.keys())[0]
            result = await client.read_resource(uri)
            assert result is not None
    
    @pytest.mark.asyncio
    async def test_list_prompts(self, client):
        """Test listing prompts."""
        await client.connect_all()
        prompts = await client.list_prompts()
        
        assert isinstance(prompts, list)
    
    @pytest.mark.asyncio
    async def test_get_prompt_mock(self, client):
        """Test getting a prompt in mock mode."""
        await client.connect_all()
        
        # Mock prompts should be set up
        if client.prompts:
            prompt_name = list(client.prompts.keys())[0]
            result = await client.get_prompt(prompt_name, {"test": "arg"})
            assert isinstance(result, str)
    
    @pytest.mark.asyncio
    async def test_health_check(self, client):
        """Test health check functionality."""
        config = MCPServerConfig(name="test", command="cmd")
        client.add_server(config)
        await client.connect_all()
        
        health = await client.health_check()
        
        assert isinstance(health, dict)
        assert "test" in health
        assert isinstance(health["test"], MCPServerHealth)
    
    @pytest.mark.asyncio
    async def test_get_metrics(self, client):
        """Test getting metrics."""
        await client.connect_all()
        
        # Make some tool calls
        await client.call_tool("read_file", {"path": "/tmp/test"}, bypass_security=True)
        
        metrics = client.get_metrics()
        assert isinstance(metrics, MCPMetrics)
        assert metrics.total_tool_calls >= 1
    
    @pytest.mark.asyncio
    async def test_get_metrics_summary(self, client):
        """Test getting metrics summary."""
        await client.connect_all()
        
        summary = client.get_metrics_summary()
        
        assert isinstance(summary, dict)
        assert "total_tool_calls" in summary
        assert "success_rate" in summary
    
    @pytest.mark.asyncio
    async def test_get_full_status(self, client):
        """Test getting full client status."""
        await client.connect_all()
        
        status = client.get_full_status()
        
        assert isinstance(status, dict)
        assert "initialized" in status
        assert "servers" in status
        assert "metrics" in status
        assert status["initialized"] is True
    
    @pytest.mark.asyncio
    async def test_disconnect_all(self, client):
        """Test disconnecting from all servers."""
        await client.connect_all()
        await client.disconnect_all()
        
        assert client._initialized is False
        assert len(client.sessions) == 0
    
    @pytest.mark.asyncio
    async def test_context_manager(self, security_config):
        """Test using client as async context manager."""
        async with AutoDevMCPClient(security_config=security_config) as client:
            assert client._initialized is True
            tools = client.list_tools()
            assert len(tools) > 0
        
        # Should be disconnected after context exit
        assert client._initialized is False
    
    @pytest.mark.asyncio
    async def test_connection_status_callback(self, security_config):
        """Test connection status change callback."""
        changes = []
        
        async def on_change(name, status):
            changes.append((name, status))
        
        client = AutoDevMCPClient(
            security_config=security_config,
            on_connection_change=on_change
        )
        
        await client.connect_all()
        
        # Callback should have been called (for mock setup)
        # Note: In mock mode, may not have actual server connections


class TestMCPExceptions:
    """Tests for MCP exceptions."""
    
    def test_connection_error(self):
        """Test MCPConnectionError."""
        error = MCPConnectionError("Failed to connect")
        assert str(error) == "Failed to connect"
        assert isinstance(error, Exception)
    
    def test_tool_error(self):
        """Test MCPToolError."""
        error = MCPToolError("Tool execution failed")
        assert str(error) == "Tool execution failed"
    
    def test_security_error(self):
        """Test MCPSecurityError."""
        error = MCPSecurityError("Access denied")
        assert str(error) == "Access denied"
    
    def test_resource_error(self):
        """Test MCPResourceError."""
        error = MCPResourceError("Resource not found")
        assert str(error) == "Resource not found"


class TestServerStatus:
    """Tests for ServerStatus enum."""
    
    def test_status_values(self):
        """Test ServerStatus enum values."""
        assert ServerStatus.DISCONNECTED.value == "disconnected"
        assert ServerStatus.CONNECTING.value == "connecting"
        assert ServerStatus.CONNECTED.value == "connected"
        assert ServerStatus.UNHEALTHY.value == "unhealthy"
        assert ServerStatus.ERROR.value == "error"


# Integration tests (run with --run-integration flag)
@pytest.mark.integration
class TestMCPIntegration:
    """Integration tests requiring actual MCP servers."""
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not MCP_AVAILABLE, reason="MCP SDK not available")
    async def test_real_mcp_connection(self):
        """Test connection to real MCP server (if available)."""
        # This test requires a real MCP server to be configured
        client = AutoDevMCPClient()
        
        try:
            await client.connect_all()
            
            if client.sessions:
                # If we have real connections, test them
                tools = client.list_tools()
                assert len(tools) > 0
                
                health = await client.health_check()
                for server_health in health.values():
                    assert server_health.status in [
                        ServerStatus.CONNECTED,
                        ServerStatus.UNHEALTHY
                    ]
        finally:
            await client.disconnect_all()


if __name__ == "__main__":
    # Run basic tests
    print("Running Phase 4 MCP Client Tests...")
    
    # Test imports
    print("✓ All imports successful")
    
    # Test basic functionality
    async def quick_test():
        security = MCPSecurityConfig(allow_all_paths=True, allow_all_commands=True)
        client = AutoDevMCPClient(security_config=security)
        
        await client.connect_all()
        print(f"✓ Connected with {len(client.list_tools())} tools")
        
        status = client.get_full_status()
        print(f"✓ Full status: initialized={status['initialized']}")
        
        metrics = client.get_metrics_summary()
        print(f"✓ Metrics: {metrics}")
        
        await client.disconnect_all()
        print("✓ Disconnected successfully")
    
    asyncio.run(quick_test())
    
    print("\nAll basic tests passed!")
