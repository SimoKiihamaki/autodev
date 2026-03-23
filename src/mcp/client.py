"""
MCP Client Implementation for AutoDev

Provides a client wrapper for connecting to MCP (Model Context Protocol) servers
and executing tools. Manages multiple server connections and provides a unified
interface for tool discovery and execution.

Phase 4 Enhanced Features:
- Resource support (list, read, subscribe)
- Prompts support (list, get)
- Health checking and monitoring
- Security validation
- Event callbacks and metrics
- Connection lifecycle management

As specified in Section 2.1 of the Phase 2 LLM/MCP Integration Specification.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Awaitable, Union
from enum import Enum
import asyncio
import json
import logging
from pathlib import Path
import os
import time
from datetime import datetime
from contextlib import asynccontextmanager

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


class MCPResourceError(Exception):
    """Raised when resource access fails."""
    pass


class MCPSecurityError(Exception):
    """Raised when security validation fails."""
    pass


class ServerStatus(Enum):
    """Status of an MCP server connection."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    UNHEALTHY = "unhealthy"


@dataclass
class MCPSecurityConfig:
    """
    Security configuration for MCP operations.
    
    Attributes:
        allowed_paths: List of allowed filesystem paths (empty = allow all)
        allowed_commands: List of allowed shell commands (empty = allow all)
        allow_all_paths: If True, allow all paths (overrides allowed_paths)
        allow_all_commands: If True, allow all commands (overrides allowed_commands)
        require_confirmation: Whether to require user confirmation for operations
        max_file_size_mb: Maximum file size in MB for read/write operations
        enable_sandbox: Whether to enable sandboxed execution
    """
    allowed_paths: List[str] = field(default_factory=list)
    allowed_commands: List[str] = field(default_factory=list)
    allow_all_paths: bool = False
    allow_all_commands: bool = False
    require_confirmation: bool = False
    max_file_size_mb: int = 10
    enable_sandbox: bool = False
    
    def is_path_allowed(self, path: str) -> bool:
        """Check if a path is within allowed directories."""
        if self.allow_all_paths:
            return True
        if not self.allowed_paths:
            return True
        try:
            abs_path = Path(path).resolve()
            for allowed in self.allowed_paths:
                allowed_abs = Path(allowed).resolve()
                if str(abs_path).startswith(str(allowed_abs)):
                    return True
            return False
        except Exception:
            return False
    
    def is_command_allowed(self, command: str) -> bool:
        """Check if a command is in the allowed list."""
        if self.allow_all_commands:
            return True
        if not self.allowed_commands:
            return True  # Allow all if no whitelist
        base_cmd = command.split()[0] if command else ""
        return base_cmd in self.allowed_commands


@dataclass
class MCPResourceInfo:
    """
    Information about an MCP resource.
    
    Attributes:
        uri: Resource URI
        name: Human-readable name
        description: Resource description
        mime_type: MIME type of the resource
        server_name: Name of the server providing this resource
    """
    uri: str
    name: str
    description: str = ""
    mime_type: str = ""
    server_name: str = ""


@dataclass
class MCPPromptInfo:
    """
    Information about an MCP prompt template.
    
    Attributes:
        name: Prompt name
        description: Prompt description
        arguments: List of argument definitions
        server_name: Name of the server providing this prompt
    """
    name: str
    description: str = ""
    arguments: List[Dict[str, Any]] = field(default_factory=list)
    server_name: str = ""


@dataclass
class MCPServerHealth:
    """
    Health status of an MCP server.
    
    Attributes:
        server_name: Name of the server
        status: Current status
        last_check: Timestamp of last health check
        latency_ms: Response latency in milliseconds
        error_message: Error message if unhealthy
        tools_available: Number of available tools
        resources_available: Number of available resources
    """
    server_name: str
    status: ServerStatus = ServerStatus.DISCONNECTED
    last_check: Optional[datetime] = None
    latency_ms: float = 0.0
    error_message: Optional[str] = None
    tools_available: int = 0
    resources_available: int = 0


@dataclass
class MCPMetrics:
    """
    Metrics collected for MCP operations.
    
    Attributes:
        total_tool_calls: Total number of tool calls
        successful_tool_calls: Number of successful tool calls
        failed_tool_calls: Number of failed tool calls
        total_resource_reads: Total number of resource reads
        total_prompt_uses: Total number of prompt uses
        total_bytes_transferred: Total bytes transferred
        average_latency_ms: Average operation latency
    """
    total_tool_calls: int = 0
    successful_tool_calls: int = 0
    failed_tool_calls: int = 0
    total_resource_reads: int = 0
    total_prompt_uses: int = 0
    total_bytes_transferred: int = 0
    average_latency_ms: float = 0.0
    _latency_samples: List[float] = field(default_factory=list)
    
    def record_tool_call(self, success: bool, latency_ms: float) -> None:
        """Record a tool call result."""
        self.total_tool_calls += 1
        if success:
            self.successful_tool_calls += 1
        else:
            self.failed_tool_calls += 1
        self._record_latency(latency_ms)
    
    def record_resource_read(self, bytes_count: int, latency_ms: float) -> None:
        """Record a resource read."""
        self.total_resource_reads += 1
        self.total_bytes_transferred += bytes_count
        self._record_latency(latency_ms)
    
    def record_prompt_use(self, latency_ms: float) -> None:
        """Record a prompt use."""
        self.total_prompt_uses += 1
        self._record_latency(latency_ms)
    
    def _record_latency(self, latency_ms: float) -> None:
        """Record latency and update average."""
        self._latency_samples.append(latency_ms)
        if len(self._latency_samples) > 100:
            self._latency_samples = self._latency_samples[-100:]
        self.average_latency_ms = sum(self._latency_samples) / len(self._latency_samples)


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
    
    Phase 4 Features:
    - Multiple server connection management
    - Tool discovery and registration
    - Resource support (list, read, subscribe)
    - Prompt template support
    - Health checking and monitoring
    - Security validation
    - Event callbacks and metrics
    - Namespaced tool names (server.tool)
    - Configuration file support
    - Graceful fallback when MCP unavailable
    
    Example:
        >>> client = AutoDevMCPClient("~/.config/autodev/mcp_config.json")
        >>> await client.connect_all()
        >>> tools = client.get_tools_for_llm()
        >>> result = await client.call_tool("read_file", {"path": "test.py"})
        >>> resources = await client.list_resources()
        >>> health = await client.health_check()
        >>> await client.disconnect_all()
    """
    
    def __init__(
        self,
        config_path: str = "~/.config/autodev/mcp_config.json",
        security_config: Optional[MCPSecurityConfig] = None,
        on_tool_call: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None,
        on_resource_access: Optional[Callable[[str, str], Awaitable[None]]] = None,
        on_connection_change: Optional[Callable[[str, ServerStatus], Awaitable[None]]] = None,
    ):
        """
        Initialize MCP client.
        
        Args:
            config_path: Path to MCP configuration file
            security_config: Security configuration for operations
            on_tool_call: Async callback for tool calls (name, arguments)
            on_resource_access: Async callback for resource access (uri, operation)
            on_connection_change: Async callback for connection status changes
        """
        self.config_path = Path(config_path).expanduser()
        self.security_config = security_config or MCPSecurityConfig()
        
        # Server and session management
        self.servers: Dict[str, MCPServerConfig] = {}
        self.sessions: Dict[str, Any] = {}  # ClientSession when MCP available
        self._server_health: Dict[str, MCPServerHealth] = {}
        
        # Tools, resources, prompts
        self.tools: Dict[str, MCPToolInfo] = {}
        self.resources: Dict[str, MCPResourceInfo] = {}
        self.prompts: Dict[str, MCPPromptInfo] = {}
        
        # State tracking
        self._initialized = False
        self._connection_errors: Dict[str, str] = {}
        self._metrics = MCPMetrics()
        
        # Callbacks
        self._on_tool_call = on_tool_call
        self._on_resource_access = on_resource_access
        self._on_connection_change = on_connection_change
        
        # Health check task
        self._health_check_task: Optional[asyncio.Task] = None
        self._health_check_interval: int = 30  # seconds
        
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
            self._setup_mock_resources()
            self._setup_mock_prompts()
            return
        
        connected_count = 0
        for name, config in self.servers.items():
            if not config.enabled:
                logger.info(f"Skipping disabled server: {name}")
                self._update_server_health(name, ServerStatus.DISCONNECTED)
                continue
            
            if not config.auto_start:
                logger.debug(f"Skipping non-auto-start server: {name}")
                continue
            
            try:
                await self._notify_connection_change(name, ServerStatus.CONNECTING)
                await self.connect_server(name, config)
                connected_count += 1
                self._update_server_health(name, ServerStatus.CONNECTED)
            except Exception as e:
                error_msg = str(e)
                self._connection_errors[name] = error_msg
                self._update_server_health(name, ServerStatus.ERROR, error_msg)
                logger.error(f"Failed to connect to {name}: {error_msg}")
        
        self._initialized = True
        logger.info(
            f"Connected to {connected_count}/{len(self.servers)} MCP servers"
        )
        
        # Set up mock tools if no connections succeeded
        if connected_count == 0:
            logger.warning("No MCP servers connected, using mock tools")
            self._setup_mock_tools()
            self._setup_mock_resources()
            self._setup_mock_prompts()
        
        # Start health check task
        self._start_health_check_task()
    
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
            
            # Discover tools, resources, and prompts
            await self._discover_tools(name, session)
            await self._discover_resources(name, session)
            await self._discover_prompts(name, session)
            
            # Initialize health status
            self._server_health[name] = MCPServerHealth(
                server_name=name,
                status=ServerStatus.CONNECTED,
                last_check=datetime.utcnow(),
                tools_available=len([t for t in self.tools.values() if t.server_name == name]),
                resources_available=len([r for r in self.resources.values() if r.server_name == name])
            )
            
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
    
    async def _discover_resources(self, server_name: str, session: Any) -> None:
        """
        Discover resources available from a server.
        
        Args:
            server_name: Name of the server
            session: Connected session
        """
        if not hasattr(session, 'list_resources'):
            logger.debug(f"Server {server_name} does not support resources")
            return
        
        try:
            resources_list = await session.list_resources()
            
            for resource in resources_list.resources:
                resource_info = MCPResourceInfo(
                    uri=resource.uri,
                    name=getattr(resource, 'name', resource.uri),
                    description=getattr(resource, 'description', ''),
                    mime_type=getattr(resource, 'mimeType', ''),
                    server_name=server_name
                )
                
                # Register resource with namespaced name
                full_uri = f"{server_name}:{resource.uri}"
                self.resources[full_uri] = resource_info
                # Also register without namespace if no conflict
                if resource.uri not in self.resources:
                    self.resources[resource.uri] = resource_info
                
                logger.debug(f"Discovered resource: {full_uri}")
            
            logger.info(
                f"Discovered {len(resources_list.resources)} resources from {server_name}"
            )
            
        except Exception as e:
            logger.debug(f"Failed to discover resources from {server_name}: {e}")
    
    async def _discover_prompts(self, server_name: str, session: Any) -> None:
        """
        Discover prompts available from a server.
        
        Args:
            server_name: Name of the server
            session: Connected session
        """
        if not hasattr(session, 'list_prompts'):
            logger.debug(f"Server {server_name} does not support prompts")
            return
        
        try:
            prompts_list = await session.list_prompts()
            
            for prompt in prompts_list.prompts:
                prompt_info = MCPPromptInfo(
                    name=prompt.name,
                    description=getattr(prompt, 'description', ''),
                    arguments=getattr(prompt, 'arguments', []),
                    server_name=server_name
                )
                
                # Register prompt with namespaced name
                full_name = f"{server_name}.{prompt.name}"
                self.prompts[full_name] = prompt_info
                # Also register without namespace if no conflict
                if prompt.name not in self.prompts:
                    self.prompts[prompt.name] = prompt_info
                
                logger.debug(f"Discovered prompt: {full_name}")
            
            logger.info(
                f"Discovered {len(prompts_list.prompts)} prompts from {server_name}"
            )
            
        except Exception as e:
            logger.debug(f"Failed to discover prompts from {server_name}: {e}")
    
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
    
    def _setup_mock_resources(self) -> None:
        """Set up mock resources for testing without real MCP servers."""
        mock_resources = [
            ("file:///workspace/README.md", "README.md", "Project documentation", "text/markdown", "filesystem"),
            ("file:///workspace/src/main.py", "main.py", "Main entry point", "text/x-python", "filesystem"),
            ("file:///workspace/config.json", "config.json", "Configuration file", "application/json", "filesystem"),
        ]
        
        for uri, name, desc, mime_type, server in mock_resources:
            resource_info = MCPResourceInfo(
                uri=uri,
                name=name,
                description=desc,
                mime_type=mime_type,
                server_name=server
            )
            self.resources[uri] = resource_info
            self.resources[f"{server}:{uri}"] = resource_info
        
        logger.info(f"Set up {len(mock_resources)} mock resources")
    
    def _setup_mock_prompts(self) -> None:
        """Set up mock prompts for testing without real MCP servers."""
        mock_prompts = [
            ("code_review", "Generate a code review prompt", [], "reviewer"),
            ("generate_tests", "Generate unit tests for code", [
                {"name": "file_path", "description": "Path to the file", "required": True}
            ], "tester"),
            ("explain_code", "Explain what a piece of code does", [
                {"name": "code", "description": "Code to explain", "required": True}
            ], "coder"),
        ]
        
        for name, desc, args, server in mock_prompts:
            prompt_info = MCPPromptInfo(
                name=name,
                description=desc,
                arguments=args,
                server_name=server
            )
            self.prompts[name] = prompt_info
            self.prompts[f"{server}.{name}"] = prompt_info
        
        logger.info(f"Set up {len(mock_prompts)} mock prompts")
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        bypass_security: bool = False
    ) -> Any:
        """
        Call an MCP tool.
        
        Args:
            tool_name: Name of the tool (can include server prefix)
            arguments: Tool arguments
            bypass_security: If True, skip security validation
            
        Returns:
            Tool result
            
        Raises:
            RuntimeError: If client not initialized
            ValueError: If tool not found
            MCPSecurityError: If security validation fails
            MCPToolError: If tool execution fails
        """
        if not self._initialized:
            raise RuntimeError("MCP client not initialized. Call connect_all() first.")
        
        start_time = time.time()
        
        # Look up tool
        if tool_name not in self.tools:
            raise ValueError(f"Unknown tool: {tool_name}")
        
        tool_info = self.tools[tool_name]
        
        # Security validation
        if not bypass_security:
            self._validate_tool_call(tool_info.name, arguments)
        
        # Notify callback
        if self._on_tool_call:
            await self._on_tool_call(tool_name, arguments)
        
        # Check if we have a real session
        session = self.sessions.get(tool_info.server_name)
        
        try:
            if session is None:
                # Use mock execution
                result = await self._mock_tool_call(tool_info.name, arguments)
            else:
                logger.info(f"Calling tool {tool_name} on {tool_info.server_name}")
                
                # Call tool via MCP
                mcp_result = await session.call_tool(tool_info.name, arguments)
                
                # Parse result
                if mcp_result.content and len(mcp_result.content) > 0:
                    content = mcp_result.content[0]
                    if hasattr(content, 'type'):
                        if content.type == "text":
                            result = content.text
                        elif content.type == "resource":
                            result = content.resource
                        else:
                            result = content
                    else:
                        result = content
                else:
                    result = None
            
            # Record metrics
            latency_ms = (time.time() - start_time) * 1000
            self._metrics.record_tool_call(True, latency_ms)
            
            return result
            
        except Exception as e:
            # Record failed call
            latency_ms = (time.time() - start_time) * 1000
            self._metrics.record_tool_call(False, latency_ms)
            
            error_msg = f"Tool {tool_name} failed: {e}"
            logger.error(error_msg)
            raise MCPToolError(error_msg)
    
    def _validate_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> None:
        """
        Validate tool call against security configuration.
        
        Args:
            tool_name: Name of the tool
            arguments: Tool arguments
            
        Raises:
            MCPSecurityError: If validation fails
        """
        # Validate path arguments
        path_keys = ["path", "file_path", "directory", "root"]
        for key in path_keys:
            if key in arguments:
                path = arguments[key]
                if not self.security_config.is_path_allowed(path):
                    raise MCPSecurityError(
                        f"Access to path '{path}' is not allowed by security configuration"
                    )
        
        # Validate command arguments
        if tool_name == "execute_command" or "command" in arguments:
            command = arguments.get("command", "")
            if not self.security_config.is_command_allowed(command):
                raise MCPSecurityError(
                    f"Command '{command}' is not allowed by security configuration"
                )
    
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
    
    def add_server(self, config: MCPServerConfig) -> None:
        """
        Add a server configuration.
        
        Args:
            config: Server configuration to add
        """
        self.servers[config.name] = config
        logger.info(f"Added server configuration: {config.name}")
    
    def remove_server(self, name: str) -> bool:
        """
        Remove a server configuration.
        
        Args:
            name: Server name to remove
            
        Returns:
            True if server was removed, False if not found
        """
        if name in self.servers:
            del self.servers[name]
            logger.info(f"Removed server configuration: {name}")
            return True
        return False
    
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
    
    # Connection management methods moved to end of file (Phase 4 enhanced versions)
    
    # =========================================================================
    # Phase 4: Resource Support
    # =========================================================================
    
    async def list_resources(self, server_name: Optional[str] = None) -> List[MCPResourceInfo]:
        """
        List available resources from MCP servers.
        
        Args:
            server_name: Optional server name to filter resources
            
        Returns:
            List of MCPResourceInfo objects
        """
        if server_name:
            return [
                info for key, info in self.resources.items()
                if info.server_name == server_name and ":" not in key
            ]
        
        # Return unique resources (without namespaced duplicates)
        seen_uris = set()
        result = []
        for key, info in self.resources.items():
            if ":" not in key and info.uri not in seen_uris:
                seen_uris.add(info.uri)
                result.append(info)
        return result
    
    async def read_resource(
        self,
        uri: str,
        bypass_security: bool = False
    ) -> Union[str, bytes]:
        """
        Read a resource from an MCP server.
        
        Args:
            uri: Resource URI
            bypass_security: If True, skip security validation
            
        Returns:
            Resource content (string or bytes)
            
        Raises:
            RuntimeError: If client not initialized
            MCPResourceError: If resource not found or read fails
            MCPSecurityError: If security validation fails
        """
        if not self._initialized:
            raise RuntimeError("MCP client not initialized. Call connect_all() first.")
        
        start_time = time.time()
        
        # Look up resource
        if uri not in self.resources:
            raise MCPResourceError(f"Unknown resource: {uri}")
        
        resource_info = self.resources[uri]
        
        # Security validation for file URIs
        if not bypass_security and uri.startswith("file://"):
            path = uri[7:]  # Remove file:// prefix
            if not self.security_config.is_path_allowed(path):
                raise MCPSecurityError(
                    f"Access to path '{path}' is not allowed by security configuration"
                )
        
        # Notify callback
        if self._on_resource_access:
            await self._on_resource_access(uri, "read")
        
        # Check if we have a real session
        session = self.sessions.get(resource_info.server_name)
        
        try:
            if session is None:
                # Use mock
                result = await self._mock_resource_read(uri)
            elif hasattr(session, 'read_resource'):
                result = await session.read_resource(uri)
                if hasattr(result, 'content'):
                    result = result.content
            else:
                result = await self._mock_resource_read(uri)
            
            # Record metrics
            latency_ms = (time.time() - start_time) * 1000
            bytes_count = len(result) if isinstance(result, (str, bytes)) else 0
            self._metrics.record_resource_read(bytes_count, latency_ms)
            
            return result
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            self._metrics.record_resource_read(0, latency_ms)
            raise MCPResourceError(f"Failed to read resource {uri}: {e}")
    
    async def _mock_resource_read(self, uri: str) -> str:
        """Mock resource read for testing."""
        logger.info(f"Mock resource read: {uri}")
        if uri.startswith("file://"):
            path = uri[7:]
            try:
                actual_path = Path(path)
                if actual_path.exists():
                    content = actual_path.read_text()
                    return content[:1000]  # Limit size
            except Exception:
                pass
        return f"[Mock: Content of resource {uri}]"
    
    # =========================================================================
    # Phase 4: Prompt Support
    # =========================================================================
    
    async def list_prompts(self, server_name: Optional[str] = None) -> List[MCPPromptInfo]:
        """
        List available prompts from MCP servers.
        
        Args:
            server_name: Optional server name to filter prompts
            
        Returns:
            List of MCPPromptInfo objects
        """
        if server_name:
            return [
                info for key, info in self.prompts.items()
                if info.server_name == server_name and "." not in key
            ]
        
        # Return unique prompts (without namespaced duplicates)
        seen_names = set()
        result = []
        for key, info in self.prompts.items():
            if "." not in key and info.name not in seen_names:
                seen_names.add(info.name)
                result.append(info)
        return result
    
    async def get_prompt(
        self,
        prompt_name: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Get a rendered prompt template from an MCP server.
        
        Args:
            prompt_name: Name of the prompt template
            arguments: Arguments to fill in the template
            
        Returns:
            Rendered prompt string
            
        Raises:
            RuntimeError: If client not initialized
            MCPResourceError: If prompt not found or retrieval fails
        """
        if not self._initialized:
            raise RuntimeError("MCP client not initialized. Call connect_all() first.")
        
        start_time = time.time()
        arguments = arguments or {}
        
        # Look up prompt
        if prompt_name not in self.prompts:
            raise MCPResourceError(f"Unknown prompt: {prompt_name}")
        
        prompt_info = self.prompts[prompt_name]
        
        # Check if we have a real session
        session = self.sessions.get(prompt_info.server_name)
        
        try:
            if session is None:
                # Use mock
                result = await self._mock_get_prompt(prompt_name, arguments)
            elif hasattr(session, 'get_prompt'):
                mcp_result = await session.get_prompt(prompt_info.name, arguments)
                if hasattr(mcp_result, 'messages'):
                    # Combine messages into a single prompt
                    result = "\n\n".join(
                        msg.get("content", "") for msg in mcp_result.messages
                    )
                else:
                    result = str(mcp_result)
            else:
                result = await self._mock_get_prompt(prompt_name, arguments)
            
            # Record metrics
            latency_ms = (time.time() - start_time) * 1000
            self._metrics.record_prompt_use(latency_ms)
            
            return result
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            self._metrics.record_prompt_use(latency_ms)
            raise MCPResourceError(f"Failed to get prompt {prompt_name}: {e}")
    
    async def _mock_get_prompt(self, prompt_name: str, arguments: Dict[str, Any]) -> str:
        """Mock prompt retrieval for testing."""
        logger.info(f"Mock prompt get: {prompt_name} with {arguments}")
        
        if prompt_name == "code_review":
            return "Please review the following code for correctness, quality, and security:\n\n{code}"
        elif prompt_name == "generate_tests":
            file_path = arguments.get("file_path", "unknown")
            return f"Generate comprehensive unit tests for the code in {file_path}"
        elif prompt_name == "explain_code":
            code = arguments.get("code", "")
            return f"Explain what the following code does:\n\n{code}"
        else:
            return f"[Mock: Prompt template for {prompt_name}]"
    
    # =========================================================================
    # Phase 4: Health Checking
    # =========================================================================
    
    async def health_check(self, server_name: Optional[str] = None) -> Dict[str, MCPServerHealth]:
        """
        Perform health check on MCP servers.
        
        Args:
            server_name: Optional specific server to check
            
        Returns:
            Dictionary of server name to health status
        """
        results = {}
        
        servers_to_check = [server_name] if server_name else list(self.servers.keys())
        
        for name in servers_to_check:
            if name not in self.servers:
                continue
            
            start_time = time.time()
            config = self.servers[name]
            session = self.sessions.get(name)
            
            if not config.enabled:
                health = MCPServerHealth(
                    server_name=name,
                    status=ServerStatus.DISCONNECTED,
                    last_check=datetime.utcnow()
                )
            elif session is None:
                health = MCPServerHealth(
                    server_name=name,
                    status=ServerStatus.DISCONNECTED,
                    last_check=datetime.utcnow(),
                    error_message=self._connection_errors.get(name, "Not connected")
                )
            else:
                try:
                    # Try to list tools as a health check
                    if hasattr(session, 'list_tools'):
                        await session.list_tools()
                    
                    latency_ms = (time.time() - start_time) * 1000
                    health = MCPServerHealth(
                        server_name=name,
                        status=ServerStatus.CONNECTED,
                        last_check=datetime.utcnow(),
                        latency_ms=latency_ms,
                        tools_available=len([t for t in self.tools.values() if t.server_name == name]),
                        resources_available=len([r for r in self.resources.values() if r.server_name == name])
                    )
                except Exception as e:
                    health = MCPServerHealth(
                        server_name=name,
                        status=ServerStatus.UNHEALTHY,
                        last_check=datetime.utcnow(),
                        error_message=str(e)
                    )
            
            results[name] = health
            self._server_health[name] = health
        
        return results
    
    def get_server_health(self, server_name: str) -> Optional[MCPServerHealth]:
        """
        Get cached health status for a server.
        
        Args:
            server_name: Name of the server
            
        Returns:
            MCPServerHealth or None if not available
        """
        return self._server_health.get(server_name)
    
    def _update_server_health(
        self,
        server_name: str,
        status: ServerStatus,
        error_message: Optional[str] = None
    ) -> None:
        """Update server health status."""
        existing = self._server_health.get(server_name)
        
        if existing:
            existing.status = status
            existing.last_check = datetime.utcnow()
            if error_message:
                existing.error_message = error_message
        else:
            self._server_health[server_name] = MCPServerHealth(
                server_name=server_name,
                status=status,
                last_check=datetime.utcnow(),
                error_message=error_message
            )
        
        # Notify callback
        if self._on_connection_change:
            asyncio.create_task(self._on_connection_change(server_name, status))
    
    async def _notify_connection_change(self, server_name: str, status: ServerStatus) -> None:
        """Notify connection change callback."""
        if self._on_connection_change:
            try:
                await self._on_connection_change(server_name, status)
            except Exception as e:
                logger.error(f"Connection change callback error: {e}")
    
    def _start_health_check_task(self) -> None:
        """Start background health check task."""
        if self._health_check_task is not None:
            return
        
        async def health_check_loop():
            while self._initialized:
                try:
                    await asyncio.sleep(self._health_check_interval)
                    if self._initialized:
                        await self.health_check()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Health check loop error: {e}")
        
        try:
            self._health_check_task = asyncio.create_task(health_check_loop())
        except RuntimeError:
            # No event loop running
            pass
    
    def _stop_health_check_task(self) -> None:
        """Stop background health check task."""
        if self._health_check_task is not None:
            self._health_check_task.cancel()
            self._health_check_task = None
    
    # =========================================================================
    # Phase 4: Metrics and Statistics
    # =========================================================================
    
    def get_metrics(self) -> MCPMetrics:
        """
        Get collected metrics.
        
        Returns:
            MCPMetrics object with usage statistics
        """
        return self._metrics
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """
        Get metrics as a summary dictionary.
        
        Returns:
            Dictionary with metrics summary
        """
        return {
            "total_tool_calls": self._metrics.total_tool_calls,
            "successful_tool_calls": self._metrics.successful_tool_calls,
            "failed_tool_calls": self._metrics.failed_tool_calls,
            "success_rate": (
                self._metrics.successful_tool_calls / self._metrics.total_tool_calls * 100
                if self._metrics.total_tool_calls > 0 else 0
            ),
            "total_resource_reads": self._metrics.total_resource_reads,
            "total_prompt_uses": self._metrics.total_prompt_uses,
            "total_bytes_transferred": self._metrics.total_bytes_transferred,
            "average_latency_ms": self._metrics.average_latency_ms,
        }
    
    def reset_metrics(self) -> None:
        """Reset collected metrics."""
        self._metrics = MCPMetrics()
    
    def get_full_status(self) -> Dict[str, Any]:
        """
        Get comprehensive status including health, metrics, and connections.
        
        Returns:
            Dictionary with full client status
        """
        return {
            "initialized": self._initialized,
            "mcp_available": MCP_AVAILABLE,
            "servers": {
                name: {
                    "connected": name in self.sessions,
                    "enabled": config.enabled,
                    "health": self._server_health.get(name).__dict__ if name in self._server_health else None,
                    "error": self._connection_errors.get(name)
                }
                for name, config in self.servers.items()
            },
            "tools_count": len(self.list_tools()),
            "resources_count": len(self.resources),
            "prompts_count": len(self.prompts),
            "metrics": self.get_metrics_summary(),
        }
    
    # =========================================================================
    # Phase 4: Enhanced Connection Management
    # =========================================================================
    
    async def disconnect_all(self) -> None:
        """
        Disconnect from all servers.
        
        Properly closes all sessions and clears state.
        """
        # Stop health check task
        self._stop_health_check_task()
        
        for name, session in list(self.sessions.items()):
            try:
                if hasattr(session, 'close'):
                    await session.close()
                await self._notify_connection_change(name, ServerStatus.DISCONNECTED)
                logger.info(f"Disconnected from {name}")
            except Exception as e:
                logger.error(f"Error disconnecting from {name}: {e}")
        
        self.sessions.clear()
        self.tools.clear()
        self.resources.clear()
        self.prompts.clear()
        self._initialized = False
        self._connection_errors.clear()
        self._server_health.clear()
    
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
            await self._notify_connection_change(name, ServerStatus.CONNECTING)
            await self.connect_server(name, config)
            self._update_server_health(name, ServerStatus.CONNECTED)
            return True
        except Exception as e:
            self._connection_errors[name] = str(e)
            self._update_server_health(name, ServerStatus.ERROR, str(e))
            logger.error(f"Reconnection to {name} failed: {e}")
            return False
    
    @asynccontextmanager
    async def server_connection(self, name: str):
        """
        Context manager for a single server connection.
        
        Args:
            name: Server name
            
        Yields:
            The server session
        """
        if name not in self.sessions:
            raise MCPConnectionError(f"Server {name} not connected")
        
        try:
            yield self.sessions[name]
        finally:
            # Connection remains open, just cleanup context
            pass
    
    async def __aenter__(self) -> "AutoDevMCPClient":
        """Async context manager entry."""
        await self.connect_all()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect_all()
