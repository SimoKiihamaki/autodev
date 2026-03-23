"""
MCP Client Implementation for AutoDev

Provides a client wrapper for connecting to MCP (Model Context Protocol) servers
and executing tools. Manages multiple server connections and provides a unified
interface for tool discovery and execution.

As specified in Section 2.1 of the Phase 2 LLM/MCP Integration Specification.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import asyncio
import json
import logging
from pathlib import Path
import os
import time

logger = logging.getLogger(__name__)

# Try to import MCP package components
# Gracefully handle when mcp package is not installed
MCP_AVAILABLE = False
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    MCP_AVAILABLE = True
except ImportError:
    ClientSession = None
    StdioServerParameters = None
    stdio_client = None
    logger.debug("MCP package not installed. Using mock implementation.")


class MCPConnectionError(Exception):
    """Raised when connection to MCP server fails."""
    pass


class MCPToolError(Exception):
    """Raised when tool execution fails."""
    pass


@dataclass
class MCPServerConfig:
    """
    Configuration for an MCP server.
    
    Attributes:
        name: Server identifier
        command: Command to start the server
        args: Command line arguments
        env: Environment variables
        enabled: Whether server is enabled
        auto_start: Whether to auto-start on connect_all
    """
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    auto_start: bool = True
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPServerConfig":
        """Create config from dictionary."""
        return cls(
            name=data.get("name", "unknown"),
            command=data.get("command", ""),
            args=data.get("args", []),
            env=data.get("env", {}),
            enabled=data.get("enabled", True),
            auto_start=data.get("auto_start", True),
        )


@dataclass
class MCPToolInfo:
    """
    Information about an MCP tool.
    
    Attributes:
        name: Tool name
        server_name: Name of the server providing this tool
        description: Tool description
        input_schema: JSON Schema for tool input
    """
    name: str
    server_name: str
    description: str
    input_schema: Dict[str, Any]


class AutoDevMCPClient:
    """
    MCP Client for AutoDev agents.
    
    Manages connections to multiple MCP servers and provides
    a unified interface for tool discovery and execution.
    
    Features:
    - Multiple server connection management
    - Tool discovery and registration
    - Namespaced tool names (server.tool)
    - Configuration file support
    - Graceful fallback when MCP unavailable
    
    Example:
        >>> client = AutoDevMCPClient("~/.config/autodev/mcp_config.json")
        >>> await client.connect_all()
        >>> tools = client.get_tools_for_llm()
        >>> result = await client.call_tool("read_file", {"path": "test.py"})
        >>> await client.disconnect_all()
    """
    
    def __init__(self, config_path: str = "~/.config/autodev/mcp_config.json"):
        """
        Initialize MCP client.
        
        Args:
            config_path: Path to MCP configuration file
        """
        self.config_path = Path(config_path).expanduser()
        self.servers: Dict[str, MCPServerConfig] = {}
        self.sessions: Dict[str, Any] = {}  # ClientSession when MCP available
        self.tools: Dict[str, MCPToolInfo] = {}
        self._initialized = False
        self._connection_errors: Dict[str, str] = {}
        
    async def load_config(self) -> None:
        """
        Load MCP server configuration from file.
        
        Falls back to default servers if config file not found.
        """
        if not self.config_path.exists():
            logger.warning(f"MCP config not found at {self.config_path}, using defaults")
            self._load_default_servers()
            return
        
        try:
            with open(self.config_path) as f:
                config_data = json.load(f)
            
            for server_data in config_data.get("servers", []):
                server_config = MCPServerConfig.from_dict(server_data)
                self.servers[server_config.name] = server_config
            
            logger.info(f"Loaded {len(self.servers)} MCP server configurations")
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in MCP config: {e}")
            self._load_default_servers()
        except Exception as e:
            logger.error(f"Error loading MCP config: {e}")
            self._load_default_servers()
    
    def _load_default_servers(self) -> None:
        """Load default MCP servers for common operations."""
        self.servers = {
            "filesystem": MCPServerConfig(
                name="filesystem",
                command="mcp-server-filesystem",
                args=["--root", "."],
                enabled=True
            ),
            "git": MCPServerConfig(
                name="git",
                command="mcp-server-git",
                args=[],
                enabled=True
            ),
            "terminal": MCPServerConfig(
                name="terminal",
                command="mcp-server-terminal",
                args=[],
                enabled=True
            )
        }
        logger.info("Loaded default MCP server configurations")
    
    async def connect_all(self) -> None:
        """
        Connect to all enabled MCP servers.
        
        Attempts to connect to each enabled server, logging errors
        for servers that fail to connect.
        """
        if not self.servers:
            await self.load_config()
        
        if not MCP_AVAILABLE:
            logger.warning(
                "MCP package not installed. Tool execution will use mock mode. "
                "Install with: pip install mcp"
            )
            self._initialized = True
            self._setup_mock_tools()
            return
        
        connected_count = 0
        for name, config in self.servers.items():
            if not config.enabled:
                logger.info(f"Skipping disabled server: {name}")
                continue
            
            if not config.auto_start:
                logger.debug(f"Skipping non-auto-start server: {name}")
                continue
            
            try:
                await self.connect_server(name, config)
                connected_count += 1
            except Exception as e:
                error_msg = str(e)
                self._connection_errors[name] = error_msg
                logger.error(f"Failed to connect to {name}: {error_msg}")
        
        self._initialized = True
        logger.info(
            f"Connected to {connected_count}/{len(self.servers)} MCP servers"
        )
        
        # Set up mock tools if no connections succeeded
        if connected_count == 0:
            logger.warning("No MCP servers connected, using mock tools")
            self._setup_mock_tools()
    
    async def connect_server(self, name: str, config: MCPServerConfig) -> None:
        """
        Connect to a specific MCP server.
        
        Args:
            name: Server name
            config: Server configuration
            
        Raises:
            MCPConnectionError: If connection fails
        """
        logger.info(f"Connecting to MCP server: {name}")
        
        if not MCP_AVAILABLE:
            raise MCPConnectionError("MCP package not installed")
        
        try:
            server_params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env={**os.environ, **config.env}  # Merge with system env
            )
            
            # Create session using stdio transport
            read_stream, write_stream = await stdio_client(server_params)
            session = ClientSession(read_stream, write_stream)
            
            # Initialize session
            await session.initialize()
            
            self.sessions[name] = session
            
            # Discover tools
            await self._discover_tools(name, session)
            
            logger.info(f"Successfully connected to {name}")
            
        except FileNotFoundError:
            raise MCPConnectionError(
                f"Server command not found: {config.command}. "
                f"Ensure the MCP server is installed."
            )
        except Exception as e:
            raise MCPConnectionError(f"Connection failed: {e}")
    
    async def _discover_tools(self, server_name: str, session: Any) -> None:
        """
        Discover tools available from a server.
        
        Args:
            server_name: Name of the server
            session: Connected session
        """
        try:
            tools_list = await session.list_tools()
            
            for tool in tools_list.tools:
                tool_info = MCPToolInfo(
                    name=tool.name,
                    server_name=server_name,
                    description=tool.description,
                    input_schema=tool.inputSchema
                )
                
                # Register tool with namespaced name
                full_name = f"{server_name}.{tool.name}"
                self.tools[full_name] = tool_info
                
                # Also register without namespace if no conflict
                if tool.name not in self.tools:
                    self.tools[tool.name] = tool_info
                
                logger.debug(f"Discovered tool: {full_name}")
                
            logger.info(
                f"Discovered {len(tools_list.tools)} tools from {server_name}"
            )
            
        except Exception as e:
            logger.error(f"Failed to discover tools from {server_name}: {e}")
    
    def _setup_mock_tools(self) -> None:
        """Set up mock tools for testing without real MCP servers."""
        mock_tools = [
            ("read_file", "filesystem", "Read file contents", {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"}
                },
                "required": ["path"]
            }),
            ("write_file", "filesystem", "Write content to file", {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "content": {"type": "string", "description": "File content"}
                },
                "required": ["path", "content"]
            }),
            ("list_directory", "filesystem", "List directory contents", {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path"}
                },
                "required": ["path"]
            }),
            ("execute_command", "terminal", "Execute a shell command", {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to execute"}
                },
                "required": ["command"]
            }),
            ("git_status", "git", "Get repository status", {
                "type": "object",
                "properties": {},
                "required": []
            }),
        ]
        
        for name, server, desc, schema in mock_tools:
            tool_info = MCPToolInfo(
                name=name,
                server_name=server,
                description=desc,
                input_schema=schema
            )
            self.tools[name] = tool_info
            self.tools[f"{server}.{name}"] = tool_info
        
        logger.info(f"Set up {len(mock_tools)} mock tools")
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """
        Call an MCP tool.
        
        Args:
            tool_name: Name of the tool (can include server prefix)
            arguments: Tool arguments
            
        Returns:
            Tool result
            
        Raises:
            RuntimeError: If client not initialized
            ValueError: If tool not found
            MCPToolError: If tool execution fails
        """
        if not self._initialized:
            raise RuntimeError("MCP client not initialized. Call connect_all() first.")
        
        # Look up tool
        if tool_name not in self.tools:
            raise ValueError(f"Unknown tool: {tool_name}")
        
        tool_info = self.tools[tool_name]
        
        # Check if we have a real session
        session = self.sessions.get(tool_info.server_name)
        
        if session is None:
            # Use mock execution
            return await self._mock_tool_call(tool_info.name, arguments)
        
        try:
            logger.info(f"Calling tool {tool_name} on {tool_info.server_name}")
            
            # Call tool via MCP
            result = await session.call_tool(tool_info.name, arguments)
            
            # Parse result
            if result.content and len(result.content) > 0:
                content = result.content[0]
                if hasattr(content, 'type'):
                    if content.type == "text":
                        return content.text
                    elif content.type == "resource":
                        return content.resource
                return content
            
            return None
            
        except Exception as e:
            error_msg = f"Tool {tool_name} failed: {e}"
            logger.error(error_msg)
            raise MCPToolError(error_msg)
    
    async def _mock_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> str:
        """
        Mock tool execution for testing.
        
        Args:
            tool_name: Name of the tool
            arguments: Tool arguments
            
        Returns:
            Mock result string
        """
        logger.info(f"Mock tool call: {tool_name} with {arguments}")
        
        # Simulate some realistic behavior
        if tool_name == "read_file":
            path = arguments.get("path", "unknown")
            # Actually try to read the file for more realistic mock
            try:
                actual_path = Path(path).expanduser()
                if actual_path.exists():
                    return actual_path.read_text()[:1000]  # Limit size
            except Exception:
                pass
            return f"[Mock: Contents of {path}]"
        
        elif tool_name == "write_file":
            path = arguments.get("path", "unknown")
            content = arguments.get("content", "")
            return f"[Mock: Wrote {len(content)} bytes to {path}]"
        
        elif tool_name == "list_directory":
            path = arguments.get("path", ".")
            return f"[Mock: Directory listing for {path}]"
        
        elif tool_name == "execute_command":
            cmd = arguments.get("command", "")
            return f"[Mock: Executed '{cmd}']"
        
        elif tool_name == "git_status":
            return "[Mock: Git status - clean working tree]"
        
        else:
            return f"[Mock: Tool {tool_name} called with {arguments}]"
    
    def get_tools_for_llm(self) -> List[Any]:
        """
        Get tool definitions in format suitable for LLM.
        
        Returns:
            List of ToolDefinition objects
        """
        # Import here to avoid circular imports
        # Handle both package import and standalone usage
        try:
            from ..llm.base_client import ToolDefinition
        except ImportError:
            try:
                from llm.base_client import ToolDefinition
            except ImportError:
                # Create a simple dataclass if ToolDefinition not available
                from dataclasses import dataclass, field
                from typing import Dict, Any
                
                @dataclass
                class ToolDefinition:
                    name: str
                    description: str
                    input_schema: Dict[str, Any]
                    mcp_server: str = ""
                # Store for future use
                globals()['ToolDefinition'] = ToolDefinition
        
        ToolDefinition = globals().get('ToolDefinition') or ToolDefinition
        
        # Use a set to avoid duplicates from namespaced names
        seen_names = set()
        tools = []
        
        for name, info in self.tools.items():
            # Skip if we've already added this tool
            base_name = name.split('.')[-1] if '.' in name else name
            if base_name in seen_names:
                continue
            seen_names.add(base_name)
            
            tools.append(ToolDefinition(
                name=base_name,
                description=info.description,
                input_schema=info.input_schema,
                mcp_server=info.server_name
            ))
        
        return tools
    
    def get_tool_info(self, tool_name: str) -> Optional[MCPToolInfo]:
        """
        Get information about a specific tool.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Tool info or None if not found
        """
        return self.tools.get(tool_name)
    
    def list_tools(self) -> List[str]:
        """
        List all available tool names.
        
        Returns:
            List of tool names
        """
        # Return unique base names
        seen = set()
        result = []
        for name in self.tools:
            base_name = name.split('.')[-1] if '.' in name else name
            if base_name not in seen:
                seen.add(base_name)
                result.append(base_name)
        return result
    
    def list_servers(self) -> List[str]:
        """
        List configured server names.
        
        Returns:
            List of server names
        """
        return list(self.servers.keys())
    
    def get_connection_status(self) -> Dict[str, Any]:
        """
        Get connection status for all servers.
        
        Returns:
            Dictionary with connection status
        """
        return {
            "initialized": self._initialized,
            "servers": {
                name: {
                    "connected": name in self.sessions,
                    "enabled": config.enabled,
                    "error": self._connection_errors.get(name)
                }
                for name, config in self.servers.items()
            },
            "tools_count": len(self.list_tools()),
            "mcp_available": MCP_AVAILABLE
        }
    
    async def disconnect_all(self) -> None:
        """
        Disconnect from all servers.
        
        Properly closes all sessions and clears state.
        """
        for name, session in list(self.sessions.items()):
            try:
                if hasattr(session, 'close'):
                    await session.close()
                logger.info(f"Disconnected from {name}")
            except Exception as e:
                logger.error(f"Error disconnecting from {name}: {e}")
        
        self.sessions.clear()
        self.tools.clear()
        self._initialized = False
        self._connection_errors.clear()
    
    async def reconnect_server(self, name: str) -> bool:
        """
        Reconnect to a specific server.
        
        Args:
            name: Server name
            
        Returns:
            True if reconnection successful
        """
        if name not in self.servers:
            logger.error(f"Unknown server: {name}")
            return False
        
        # Disconnect first if connected
        if name in self.sessions:
            try:
                if hasattr(self.sessions[name], 'close'):
                    await self.sessions[name].close()
            except Exception:
                pass
            del self.sessions[name]
        
        # Clear connection error
        self._connection_errors.pop(name, None)
        
        # Reconnect
        config = self.servers[name]
        if not config.enabled:
            logger.info(f"Server {name} is disabled")
            return False
        
        try:
            await self.connect_server(name, config)
            return True
        except Exception as e:
            self._connection_errors[name] = str(e)
            logger.error(f"Reconnection to {name} failed: {e}")
            return False
    
    async def __aenter__(self) -> "AutoDevMCPClient":
        """Async context manager entry."""
        await self.connect_all()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect_all()
