# AutoDev Phase 2: LLM/MCP Integration Specification

**Version:** 2.0.0  
**Created:** 2026-03-23  
**Status:** Implementation Ready  
**Depends On:** Phase 1 - Hierarchical Architecture Scaffold

---

## Executive Summary

This specification defines how AutoDev agents connect to LLM providers (Anthropic Claude API) and MCP tools to enable autonomous software development. The design follows the scaffold created in Phase 1, providing concrete implementations for the `TODO` sections marked throughout the agent codebase.

---

## 1. LLM Client Architecture

### 1.1 Design Principles

1. **Provider Abstraction**: Support multiple LLM providers with unified interface
2. **Streaming-First**: Enable real-time response streaming for long operations
3. **Context Management**: Intelligent context window utilization
4. **Cost Optimization**: Track and optimize token usage
5. **Error Resilience**: Robust retry and fallback mechanisms

### 1.2 Core Interface

```python
# src/llm/base_client.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Dict, List, Optional, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class MessageRole(Enum):
    """Message roles in conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class ChatMessage:
    """A single message in the conversation."""
    role: MessageRole
    content: str
    name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolDefinition:
    """Definition of a tool available to the LLM."""
    name: str
    description: str
    input_schema: Dict[str, Any]  # JSON Schema
    mcp_server: str  # Which MCP server provides this tool


@dataclass
class ToolUse:
    """A tool use request from the LLM."""
    id: str
    name: str
    input: Dict[str, Any]


@dataclass
class LLMResponse:
    """Response from LLM completion."""
    content: str
    tool_uses: List[ToolUse] = field(default_factory=list)
    stop_reason: str = "end_turn"  # end_turn, max_tokens, tool_use
    usage: Dict[str, int] = field(default_factory=dict)
    model: str = ""
    finish_reason: Optional[str] = None


@dataclass
class LLMConfig:
    """Configuration for LLM client."""
    provider: str = "anthropic"
    model: str = "claude-3-5-sonnet-20241022"
    max_tokens: int = 4096
    temperature: float = 0.7
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout_seconds: int = 120
    max_retries: int = 3
    retry_backoff_seconds: float = 1.0
    enable_caching: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseLLMClient(ABC):
    """
    Abstract base class for LLM clients.
    
    Provides unified interface for different LLM providers.
    """
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self._total_tokens_used = 0
        self._request_count = 0
    
    @abstractmethod
    async def complete(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Complete a conversation with the LLM.
        
        Args:
            messages: Conversation history
            tools: Available tools for tool use
            system_prompt: System prompt override
            **kwargs: Additional provider-specific parameters
            
        Returns:
            LLMResponse with content and optional tool uses
        """
        pass
    
    @abstractmethod
    async def stream_complete(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Stream completion response.
        
        Yields:
            Text chunks as they arrive
        """
        pass
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get token usage statistics."""
        return {
            "total_tokens": self._total_tokens_used,
            "request_count": self._request_count,
            "avg_tokens_per_request": (
                self._total_tokens_used / self._request_count 
                if self._request_count > 0 else 0
            )
        }
    
    def _update_usage(self, usage: Dict[str, int]) -> None:
        """Update usage statistics."""
        self._total_tokens_used += usage.get("total_tokens", 0)
        self._request_count += 1
```

### 1.3 Anthropic Claude Implementation

```python
# src/llm/anthropic_client.py

from anthropic import AsyncAnthropic
from typing import AsyncIterator, List, Optional
import logging
import asyncio

from .base_client import (
    BaseLLMClient,
    ChatMessage,
    MessageRole,
    ToolDefinition,
    ToolUse,
    LLMResponse,
    LLMConfig
)

logger = logging.getLogger(__name__)


class AnthropicClient(BaseLLMClient):
    """
    Anthropic Claude API client implementation.
    
    Supports Claude 3.5 Sonnet, Claude 3.5 Haiku, and Claude 3 Opus.
    Implements prompt caching for cost optimization.
    """
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        
        # Initialize Anthropic client
        self.client = AsyncAnthropic(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries
        )
        
        # Default system prompts for each agent role
        self._role_system_prompts = {
            "manager": self._get_manager_system_prompt(),
            "coder": self._get_coder_system_prompt(),
            "reviewer": self._get_reviewer_system_prompt(),
            "tester": self._get_tester_system_prompt()
        }
    
    async def complete(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Complete conversation using Claude API.
        
        Features:
        - Prompt caching for system messages
        - Tool use support
        - Automatic retry on rate limits
        """
        # Convert messages to Anthropic format
        anthropic_messages = self._convert_messages(messages)
        
        # Build request
        request_params = {
            "model": self.config.model,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": anthropic_messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
        }
        
        # Add system prompt
        if system_prompt:
            request_params["system"] = [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}  # Enable caching
                }
            ]
        
        # Add tools if provided
        if tools:
            request_params["tools"] = self._convert_tools(tools)
        
        try:
            # Make API call
            response = await self.client.messages.create(**request_params)
            
            # Parse response
            content_text = ""
            tool_uses = []
            
            for block in response.content:
                if block.type == "text":
                    content_text += block.text
                elif block.type == "tool_use":
                    tool_uses.append(ToolUse(
                        id=block.id,
                        name=block.name,
                        input=block.input
                    ))
            
            # Update usage stats
            self._update_usage({
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens
            })
            
            # Log cache efficiency
            if hasattr(response.usage, 'cache_read_input_tokens'):
                logger.info(
                    f"Cache efficiency: {response.usage.cache_read_input_tokens} "
                    f"tokens read from cache"
                )
            
            return LLMResponse(
                content=content_text,
                tool_uses=tool_uses,
                stop_reason=response.stop_reason,
                usage={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "cache_read_tokens": getattr(response.usage, 'cache_read_input_tokens', 0)
                },
                model=response.model
            )
            
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise
    
    async def stream_complete(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream completion from Claude."""
        
        anthropic_messages = self._convert_messages(messages)
        
        request_params = {
            "model": self.config.model,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": anthropic_messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
        }
        
        if system_prompt:
            request_params["system"] = system_prompt
        
        if tools:
            request_params["tools"] = self._convert_tools(tools)
        
        async with self.client.messages.stream(**request_params) as stream:
            async for text in stream.text_stream:
                yield text
        
        # Update usage after streaming completes
        final_message = await stream.get_final_message()
        self._update_usage({
            "total_tokens": final_message.usage.input_tokens + final_message.usage.output_tokens
        })
    
    def _convert_messages(self, messages: List[ChatMessage]) -> List[dict]:
        """Convert ChatMessage list to Anthropic format."""
        anthropic_messages = []
        
        for msg in messages:
            anthropic_msg = {
                "role": msg.role.value,
                "content": msg.content
            }
            anthropic_messages.append(anthropic_msg)
        
        return anthropic_messages
    
    def _convert_tools(self, tools: List[ToolDefinition]) -> List[dict]:
        """Convert ToolDefinition to Anthropic format."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema
            }
            for tool in tools
        ]
    
    def _get_manager_system_prompt(self) -> str:
        """Get system prompt for Manager Agent."""
        return """You are the Manager Agent in AutoDev, an autonomous software development system.

Your responsibilities:
- Decompose complex tasks into atomic subtasks
- Assign tasks to specialized workers (Coder, Reviewer, Tester)
- Monitor execution progress and handle failures
- Resolve conflicts between parallel workers
- Synthesize final results

You must:
- Think through task dependencies carefully
- Provide clear, unambiguous task specifications
- Make decisions based on quality gates and acceptance criteria
- Communicate status updates clearly

Available worker types:
- Coder: Implements features, fixes bugs, refactors code
- Reviewer: Reviews code quality, validates acceptance criteria
- Tester: Generates and executes tests

Output structured task assignments with clear specifications."""
    
    def _get_coder_system_prompt(self) -> str:
        """Get system prompt for Coder Agent."""
        return """You are the Coder Agent in AutoDev, specialized in code generation and modification.

Your capabilities:
- Implement features from specifications
- Fix bugs based on reports
- Refactor code for quality improvements
- Write documentation

You must:
- Follow existing code style and patterns
- Maintain backward compatibility when required
- Write clean, self-documenting code
- Include appropriate error handling
- Consider edge cases

Output:
1. Clear description of changes made
2. Rationale for implementation choices
3. Any assumptions or edge cases handled"""
    
    def _get_reviewer_system_prompt(self) -> str:
        """Get system prompt for Reviewer Agent."""
        return """You are the Reviewer Agent in AutoDev, responsible for quality assurance.

Your responsibilities:
- Review code changes for correctness
- Check coding standards compliance
- Identify security vulnerabilities
- Validate acceptance criteria
- Detect anti-patterns

Review checklist:
1. Correctness: Does code do what it should?
2. Quality: Is it readable and maintainable?
3. Security: Are there vulnerabilities?
4. Testing: Is coverage adequate?
5. Performance: Are there obvious issues?

Provide:
- Clear verdict: approved, needs_changes, or rejected
- Specific findings with severity levels
- Actionable recommendations"""
    
    def _get_tester_system_prompt(self) -> str:
        """Get system prompt for Tester Agent."""
        return """You are the Tester Agent in AutoDev, specialized in test generation and execution.

Your responsibilities:
- Generate comprehensive test suites
- Execute tests and analyze results
- Ensure adequate code coverage
- Identify test gaps

You must:
- Write unit tests, integration tests, and edge case tests
- Use appropriate testing frameworks
- Provide clear test results
- Suggest improvements for test coverage

Output test files and execution results."""
```

---

## 2. MCP Client Integration

### 2.1 MCP Client Architecture

```python
# src/mcp/client.py

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import asyncio
import json
import logging
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ..llm.base_client import ToolDefinition

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    auto_start: bool = True


@dataclass
class MCPToolInfo:
    """Information about an MCP tool."""
    name: str
    server_name: str
    description: str
    input_schema: Dict[str, Any]


class AutoDevMCPClient:
    """
    MCP Client for AutoDev agents.
    
    Manages connections to multiple MCP servers and provides
    a unified interface for tool discovery and execution.
    """
    
    def __init__(self, config_path: str = "~/.config/autodev/mcp_config.json"):
        self.config_path = Path(config_path).expanduser()
        self.servers: Dict[str, MCPServerConfig] = {}
        self.sessions: Dict[str, ClientSession] = {}
        self.tools: Dict[str, MCPToolInfo] = {}
        self._initialized = False
    
    async def load_config(self) -> None:
        """Load MCP server configuration."""
        if not self.config_path.exists():
            logger.warning(f"MCP config not found at {self.config_path}, using defaults")
            self._load_default_servers()
            return
        
        with open(self.config_path) as f:
            config_data = json.load(f)
        
        for server_data in config_data.get("servers", []):
            server_config = MCPServerConfig(**server_data)
            self.servers[server_config.name] = server_config
        
        logger.info(f"Loaded {len(self.servers)} MCP server configurations")
    
    def _load_default_servers(self) -> None:
        """Load default MCP servers."""
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
    
    async def connect_all(self) -> None:
        """Connect to all enabled MCP servers."""
        if not self.servers:
            await self.load_config()
        
        for name, config in self.servers.items():
            if not config.enabled:
                logger.info(f"Skipping disabled server: {name}")
                continue
            
            try:
                await self.connect_server(name, config)
            except Exception as e:
                logger.error(f"Failed to connect to {name}: {e}")
        
        self._initialized = True
        logger.info(f"Connected to {len(self.sessions)} MCP servers")
    
    async def connect_server(self, name: str, config: MCPServerConfig) -> None:
        """Connect to a specific MCP server."""
        logger.info(f"Connecting to MCP server: {name}")
        
        server_params = StdioServerParameters(
            command=config.command,
            args=config.args,
            env=config.env
        )
        
        # Create session
        read_stream, write_stream = await stdio_client(server_params)
        session = ClientSession(read_stream, write_stream)
        
        # Initialize session
        await session.initialize()
        
        self.sessions[name] = session
        
        # Discover tools
        await self._discover_tools(name, session)
    
    async def _discover_tools(self, server_name: str, session: ClientSession) -> None:
        """Discover tools available from a server."""
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
            
            logger.info(f"Discovered tool: {full_name}")
    
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
        """
        if not self._initialized:
            raise RuntimeError("MCP client not initialized. Call connect_all() first.")
        
        # Look up tool
        if tool_name not in self.tools:
            raise ValueError(f"Unknown tool: {tool_name}")
        
        tool_info = self.tools[tool_name]
        session = self.sessions.get(tool_info.server_name)
        
        if not session:
            raise RuntimeError(f"Server {tool_info.server_name} not connected")
        
        # Call tool
        logger.info(f"Calling tool {tool_name} on {tool_info.server_name}")
        result = await session.call_tool(tool_info.name, arguments)
        
        # Parse result
        if result.content and len(result.content) > 0:
            content = result.content[0]
            if content.type == "text":
                return content.text
            elif content.type == "resource":
                return content.resource
        
        return None
    
    def get_tools_for_llm(self) -> List[ToolDefinition]:
        """
        Get tool definitions in format suitable for LLM.
        
        Returns:
            List of ToolDefinition objects
        """
        return [
            ToolDefinition(
                name=name,
                description=info.description,
                input_schema=info.input_schema,
                mcp_server=info.server_name
            )
            for name, info in self.tools.items()
        ]
    
    async def disconnect_all(self) -> None:
        """Disconnect from all servers."""
        for name, session in self.sessions.items():
            try:
                await session.close()
                logger.info(f"Disconnected from {name}")
            except Exception as e:
                logger.error(f"Error disconnecting from {name}: {e}")
        
        self.sessions.clear()
        self.tools.clear()
        self._initialized = False
```

### 2.2 Required MCP Servers

AutoDev requires the following MCP servers:

#### 2.2.1 Filesystem Server

```json
{
  "name": "filesystem",
  "command": "mcp-server-filesystem",
  "args": ["--root", "/workspace"],
  "env": {}
}
```

**Tools provided:**
- `read_file`: Read file contents
- `write_file`: Write/overwrite file
- `list_directory`: List directory contents
- `create_directory`: Create directory tree
- `delete_file`: Delete file or directory
- `move_file`: Move/rename file
- `copy_file`: Copy file

#### 2.2.2 Git Server

```json
{
  "name": "git",
  "command": "mcp-server-git",
  "args": [],
  "env": {}
}
```

**Tools provided:**
- `git_status`: Get repository status
- `git_diff`: Get diff of changes
- `git_log`: View commit history
- `git_branch`: Branch operations
- `git_commit`: Create commit
- `git_checkout`: Checkout branch/commit

#### 2.2.3 Terminal Server

```json
{
  "name": "terminal",
  "command": "mcp-server-terminal",
  "args": [],
  "env": {}
}
```

**Tools provided:**
- `execute_command`: Run shell command
- `get_output`: Get command output
- `kill_process`: Terminate running process

#### 2.2.4 Optional: LSP Server

```json
{
  "name": "lsp",
  "command": "mcp-server-lsp",
  "args": ["--language", "python"],
  "env": {}
}
```

**Tools provided:**
- `go_to_definition`: Navigate to definition
- `find_references`: Find all references
- `get_completions`: Get code completions
- `get_diagnostics`: Get linting errors

---

## 3. Message Routing & Tool Execution

### 3.1 Agent Tool Execution Loop

```python
# src/agents/tool_executor.py

from typing import List, Dict, Any, Optional
import asyncio
import logging

from ..llm.base_client import ChatMessage, MessageRole, ToolUse, LLMResponse
from ..mcp.client import AutoDevMCPClient

logger = logging.getLogger(__name__)


class ToolExecutionLoop:
    """
    Manages the tool execution loop for agents.
    
    Implements the ReAct pattern:
    1. Agent receives task
    2. Agent decides to use tool
    3. Tool is executed via MCP
    4. Result is fed back to agent
    5. Loop continues until task complete
    """
    
    def __init__(
        self,
        llm_client,
        mcp_client: AutoDevMCPClient,
        max_iterations: int = 20
    ):
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        self.max_iterations = max_iterations
    
    async def execute_with_tools(
        self,
        initial_messages: List[ChatMessage],
        system_prompt: str,
        on_tool_call: Optional[callable] = None
    ) -> str:
        """
        Execute agent task with tool calling loop.
        
        Args:
            initial_messages: Initial conversation
            system_prompt: System prompt for agent
            on_tool_call: Optional callback for tool calls
            
        Returns:
            Final response from agent
        """
        messages = list(initial_messages)
        tools = self.mcp_client.get_tools_for_llm()
        
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            logger.info(f"Tool execution iteration {iteration}")
            
            # Get LLM response
            response = await self.llm_client.complete(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt
            )
            
            # Check if done
            if response.stop_reason == "end_turn" or not response.tool_uses:
                return response.content
            
            # Process tool calls
            if response.tool_uses:
                # Add assistant message with tool use
                messages.append(ChatMessage(
                    role=MessageRole.ASSISTANT,
                    content=response.content,
                    metadata={"tool_uses": [t.__dict__ for t in response.tool_uses]}
                ))
                
                # Execute each tool
                for tool_use in response.tool_uses:
                    try:
                        # Callback for logging/monitoring
                        if on_tool_call:
                            on_tool_call(tool_use.name, tool_use.input)
                        
                        # Execute tool via MCP
                        result = await self.mcp_client.call_tool(
                            tool_use.name,
                            tool_use.input
                        )
                        
                        # Add tool result to messages
                        messages.append(ChatMessage(
                            role=MessageRole.USER,
                            content=f"Tool {tool_use.name} result: {result}",
                            name=tool_use.name
                        ))
                        
                        logger.info(f"Tool {tool_use.name} executed successfully")
                        
                    except Exception as e:
                        error_msg = f"Tool {tool_use.name} failed: {str(e)}"
                        logger.error(error_msg)
                        
                        messages.append(ChatMessage(
                            role=MessageRole.USER,
                            content=error_msg,
                            name=tool_use.name
                        ))
        
        logger.warning(f"Reached max iterations ({self.max_iterations})")
        return "Task did not complete within maximum iterations"
```

### 3.2 Updated Base Agent with LLM/MCP Integration

```python
# src/agents/base.py (updated sections)

class BaseAgent(ABC):
    """
    Abstract base class for all AutoDev agents.
    
    Updated with LLM and MCP integration.
    """
    
    def __init__(
        self,
        agent_id: str = None,
        role: AgentRole = None,
        mcp_config_path: str = "~/.config/autodev/mcp_config.json",
        repo_root: str = ".",
        llm_config: Optional[LLMConfig] = None
    ):
        self.agent_id = agent_id or str(uuid.uuid4())
        self.role = role or AgentRole.CODER
        self.state = AgentState.IDLE
        self.mcp_config_path = mcp_config_path
        self.repo_root = repo_root
        
        # LLM and MCP clients
        self._llm_config = llm_config or LLMConfig()
        self._llm_client: Optional[BaseLLMClient] = None
        self._mcp_client: Optional[AutoDevMCPClient] = None
        self._tool_executor: Optional[ToolExecutionLoop] = None
        
        # Message queue for inter-agent communication
        self._message_queue: List[Any] = []
        
        # Conversation history for context
        self._conversation_history: List[ChatMessage] = []
    
    async def initialize(self) -> None:
        """
        Initialize the agent with LLM and MCP connections.
        """
        logger.info(f"Initializing {self.role.value} agent {self.agent_id}")
        
        self.update_state(AgentState.INITIALIZING)
        
        # Initialize LLM client
        if self.role == AgentRole.MANAGER:
            self._llm_config.model = "claude-3-5-sonnet-20241022"
        elif self.role == AgentRole.CODER:
            self._llm_config.model = "claude-3-5-sonnet-20241022"
        elif self.role == AgentRole.REVIEWER:
            self._llm_config.model = "claude-3-5-sonnet-20241022"
        
        self._llm_client = AnthropicClient(self._llm_config)
        
        # Initialize MCP client
        self._mcp_client = AutoDevMCPClient(self.mcp_config_path)
        await self._mcp_client.connect_all()
        
        # Initialize tool executor
        self._tool_executor = ToolExecutionLoop(
            llm_client=self._llm_client,
            mcp_client=self._mcp_client
        )
        
        self.update_state(AgentState.IDLE)
        logger.info(f"{self.role.value} agent initialized successfully")
    
    async def shutdown(self) -> None:
        """Clean shutdown."""
        logger.info(f"Shutting down {self.role.value} agent {self.agent_id}")
        
        if self._mcp_client:
            await self._mcp_client.disconnect_all()
        
        # Log usage stats
        if self._llm_client:
            stats = self._llm_client.get_usage_stats()
            logger.info(f"LLM usage: {stats}")
        
        self.update_state(AgentState.COMPLETED)
    
    async def _call_llm(
        self,
        prompt: str,
        use_tools: bool = True,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Call LLM with optional tool support.
        
        Args:
            prompt: User prompt
            use_tools: Whether to enable tool calling
            system_prompt: Optional system prompt override
            
        Returns:
            LLM response
        """
        # Add to conversation history
        self._conversation_history.append(ChatMessage(
            role=MessageRole.USER,
            content=prompt
        ))
        
        if use_tools and self._tool_executor:
            # Execute with tool loop
            response = await self._tool_executor.execute_with_tools(
                initial_messages=self._conversation_history,
                system_prompt=system_prompt or self._get_default_system_prompt(),
                on_tool_call=self._on_tool_call
            )
        else:
            # Simple completion without tools
            llm_response = await self._llm_client.complete(
                messages=self._conversation_history,
                system_prompt=system_prompt or self._get_default_system_prompt()
            )
            response = llm_response.content
        
        # Add response to history
        self._conversation_history.append(ChatMessage(
            role=MessageRole.ASSISTANT,
            content=response
        ))
        
        return response
    
    def _on_tool_call(self, tool_name: str, tool_input: Dict[str, Any]) -> None:
        """Callback when a tool is called (for logging/monitoring)."""
        logger.info(f"Agent {self.agent_id} calling tool: {tool_name}")
    
    @abstractmethod
    def _get_default_system_prompt(self) -> str:
        """Get the default system prompt for this agent type."""
        pass
```

---

## 4. Configuration & Deployment

### 4.1 Configuration File Structure

```json
// ~/.config/autodev/config.json
{
  "version": "2.0.0",
  "llm": {
    "provider": "anthropic",
    "api_key": "${ANTHROPIC_API_KEY}",
    "default_model": "claude-3-5-sonnet-20241022",
    "max_tokens": 4096,
    "temperature": 0.7,
    "enable_caching": true
  },
  "mcp": {
    "config_path": "~/.config/autodev/mcp_config.json",
    "auto_connect": true,
    "connection_timeout_seconds": 10
  },
  "agents": {
    "manager": {
      "model": "claude-3-5-sonnet-20241022",
      "max_concurrent_workers": 3,
      "task_timeout_seconds": 300
    },
    "coder": {
      "model": "claude-3-5-sonnet-20241022",
      "max_retries": 2,
      "retry_backoff_seconds": 30
    },
    "reviewer": {
      "model": "claude-3-5-sonnet-20241022",
      "strict_mode": true,
      "auto_fix_enabled": true
    }
  },
  "logging": {
    "level": "INFO",
    "file": "~/.local/share/autodev/autodev.log",
    "max_size_mb": 100,
    "backup_count": 5
  }
}
```

```json
// ~/.config/autodev/mcp_config.json
{
  "servers": [
    {
      "name": "filesystem",
      "command": "mcp-server-filesystem",
      "args": ["--root", "."],
      "env": {},
      "enabled": true,
      "auto_start": true
    },
    {
      "name": "git",
      "command": "mcp-server-git",
      "args": [],
      "env": {},
      "enabled": true,
      "auto_start": true
    },
    {
      "name": "terminal",
      "command": "mcp-server-terminal",
      "args": [],
      "env": {},
      "enabled": true,
      "auto_start": true
    }
  ],
  "security": {
    "allowed_paths": ["."],
    "allowed_commands": ["pytest", "black", "mypy", "git"],
    "require_confirmation": false
  }
}
```

### 4.2 Environment Setup

```bash
# Required environment variables
export ANTHROPIC_API_KEY="sk-ant-..."

# Optional: Override default model
export AUTODEV_DEFAULT_MODEL="claude-3-5-sonnet-20241022"

# Optional: Set log level
export AUTODEV_LOG_LEVEL="DEBUG"
```

### 4.3 Dependencies

```toml
# pyproject.toml
[project]
name = "autodev"
version = "2.0.0"
dependencies = [
    "anthropic>=0.40.0",
    "mcp>=0.9.0",
    "asyncio-compat>=0.1.0",
    "pydantic>=2.0.0",
    "python-dotenv>=1.0.0"
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "black>=24.0.0",
    "mypy>=1.8.0"
]
```

---

## 5. Implementation Roadmap

### Phase 2A: Core LLM Integration (Week 1)
- [ ] Implement `BaseLLMClient` and `LLMConfig` classes
- [ ] Implement `AnthropicClient` with streaming support
- [ ] Add conversation history management
- [ ] Implement system prompts for each agent role
- [ ] Add unit tests for LLM client

### Phase 2B: MCP Integration (Week 2)
- [ ] Implement `AutoDevMCPClient` class
- [ ] Add server configuration loading
- [ ] Implement tool discovery mechanism
- [ ] Create MCP server configuration files
- [ ] Test connection to filesystem, git, terminal servers
- [ ] Add integration tests

### Phase 2C: Tool Execution Loop (Week 3)
- [ ] Implement `ToolExecutionLoop` class
- [ ] Update `BaseAgent` to use LLM and MCP
- [ ] Implement tool call callback system
- [ ] Add error handling and retry logic
- [ ] Test end-to-end tool execution

### Phase 2D: Agent Updates (Week 4)
- [ ] Update Manager Agent with LLM integration
- [ ] Update Coder Agent with tool execution
- [ ] Update Reviewer Agent with analysis tools
- [ ] Implement task decomposition using LLM
- [ ] Add integration tests for full workflow

### Phase 2E: Testing & Documentation (Week 5)
- [ ] Write comprehensive test suite
- [ ] Create usage examples
- [ ] Document API reference
- [ ] Create deployment guide
- [ ] Performance benchmarking

---

## 6. Testing Strategy

### 6.1 Unit Tests

```python
# tests/llm/test_anthropic_client.py

import pytest
from autodev.llm import AnthropicClient, LLMConfig, ChatMessage, MessageRole

@pytest.fixture
def llm_config():
    return LLMConfig(
        api_key="test-key",
        model="claude-3-5-sonnet-20241022"
    )

@pytest.fixture
def anthropic_client(llm_config):
    return AnthropicClient(llm_config)

@pytest.mark.asyncio
async def test_complete_returns_response(anthropic_client, mocker):
    """Test basic completion."""
    # Mock Anthropic API
    mock_response = mocker.Mock()
    mock_response.content = [mocker.Mock(type="text", text="Hello!")]
    mock_response.stop_reason = "end_turn"
    mock_response.usage = mocker.Mock(
        input_tokens=10,
        output_tokens=5,
        cache_read_input_tokens=0
    )
    mock_response.model = "claude-3-5-sonnet-20241022"
    
    mocker.patch.object(
        anthropic_client.client.messages,
        'create',
        return_value=mock_response
    )
    
    messages = [ChatMessage(role=MessageRole.USER, content="Hi")]
    response = await anthropic_client.complete(messages)
    
    assert response.content == "Hello!"
    assert response.stop_reason == "end_turn"

@pytest.mark.asyncio
async def test_stream_complete_yields_chunks(anthropic_client, mocker):
    """Test streaming completion."""
    # Mock streaming
    async def mock_stream():
        yield "Hello"
        yield " "
        yield "world"
    
    mocker.patch.object(
        anthropic_client.client.messages,
        'stream',
        return_value=mock_stream()
    )
    
    messages = [ChatMessage(role=MessageRole.USER, content="Hi")]
    chunks = []
    async for chunk in anthropic_client.stream_complete(messages):
        chunks.append(chunk)
    
    assert chunks == ["Hello", " ", "world"]
```

### 6.2 Integration Tests

```python
# tests/integration/test_agent_workflow.py

import pytest
from autodev.agents import ManagerAgent, CoderAgent, ReviewerAgent
from autodev.base import TaskSpec

@pytest.mark.integration
@pytest.mark.asyncio
async def test_manager_decomposer_workflow():
    """Test full manager → coder → reviewer workflow."""
    # Create task
    task = TaskSpec(
        task_type="implement",
        specification="Add a simple hello world function",
        target_files=["hello.py"]
    )
    
    # Initialize manager
    manager = ManagerAgent()
    await manager.initialize()
    
    # Execute task
    result = await manager.execute(task)
    
    # Verify
    assert result.status == "completed"
    assert "hello.py" in result.files_modified
    
    # Cleanup
    await manager.shutdown()

@pytest.mark.integration
@pytest.mark.asyncio
async def test_coder_uses_mcp_tools():
    """Test that coder agent uses MCP tools."""
    coder = CoderAgent()
    await coder.initialize()
    
    # Create task requiring file operations
    task = TaskSpec(
        task_type="implement",
        specification="Create a file called test.txt with content 'Hello'",
        target_files=["test.txt"]
    )
    
    result = await coder.execute(task)
    
    # Verify file was created via MCP
    assert result.status == "completed"
    
    await coder.shutdown()
```

---

## 7. Security & Safety Considerations

### 7.1 API Key Management
- Never hardcode API keys
- Use environment variables or secure vaults
- Rotate keys regularly
- Monitor usage for anomalies

### 7.2 MCP Server Isolation
- Run MCP servers in isolated processes
- Limit filesystem access to workspace
- Whitelist allowed commands
- Audit all tool calls

### 7.3 Agent Constraints
- Set maximum iteration limits
- Implement timeout mechanisms
- Validate all inputs/outputs
- Log all actions for audit

### 7.4 Rate Limiting & Cost Control
```python
# Implement rate limiting
class RateLimitedLLMClient(BaseLLMClient):
    def __init__(self, config: LLMConfig, max_requests_per_minute: int = 60):
        super().__init__(config)
        self.rate_limiter = RateLimiter(max_requests_per_minute)
    
    async def complete(self, messages, tools=None, system_prompt=None, **kwargs):
        await self.rate_limiter.acquire()
        return await super().complete(messages, tools, system_prompt, **kwargs)
```

---

## 8. Performance Optimization

### 8.1 Prompt Caching
- Enable Anthropic prompt caching for system prompts
- Cache frequently used context
- Monitor cache hit rates

### 8.2 Context Window Management
```python
class ContextManager:
    """Manages context window efficiently."""
    
    def __init__(self, max_tokens: int = 200000):
        self.max_tokens = max_tokens
        self.current_tokens = 0
        self.messages = []
    
    def add_message(self, message: ChatMessage) -> bool:
        """Add message if fits in context window."""
        msg_tokens = self._estimate_tokens(message.content)
        
        if self.current_tokens + msg_tokens > self.max_tokens:
            # Prune old messages
            self._prune_messages(msg_tokens)
        
        self.messages.append(message)
        self.current_tokens += msg_tokens
        return True
    
    def _prune_messages(self, needed_tokens: int) -> None:
        """Remove old messages to make room."""
        while self.current_tokens + needed_tokens > self.max_tokens * 0.8:
            if not self.messages:
                break
            removed = self.messages.pop(0)
            self.current_tokens -= self._estimate_tokens(removed.content)
```

### 8.3 Parallel Tool Execution
```python
async def execute_tools_parallel(
    tool_calls: List[ToolUse],
    mcp_client: AutoDevMCPClient
) -> List[Any]:
    """Execute multiple tools in parallel when possible."""
    tasks = [
        mcp_client.call_tool(tc.name, tc.input)
        for tc in tool_calls
    ]
    return await asyncio.gather(*tasks, return_exceptions=True)
```

---

## 9. Monitoring & Observability

### 9.1 Logging Strategy

```python
# Configure structured logging
import logging
import json
from datetime import datetime

class StructuredLogger:
    """JSON-structured logging for observability."""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def log_event(self, event_type: str, **kwargs):
        """Log structured event."""
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            **kwargs
        }
        self.logger.info(json.dumps(event))
    
    def log_tool_call(self, tool_name: str, agent_id: str, input: dict):
        self.log_event(
            "tool_call",
            tool_name=tool_name,
            agent_id=agent_id,
            input_size=len(str(input))
        )
    
    def log_llm_call(self, model: str, tokens_used: int, duration_ms: float):
        self.log_event(
            "llm_call",
            model=model,
            tokens_used=tokens_used,
            duration_ms=duration_ms
        )
```

### 9.2 Metrics Collection

```python
# Metrics to track
METRICS = {
    "llm_requests_total": "Counter",
    "llm_tokens_used_total": "Counter",
    "llm_request_duration_seconds": "Histogram",
    "tool_calls_total": "Counter",
    "tool_call_duration_seconds": "Histogram",
    "agent_task_duration_seconds": "Histogram",
    "agent_tasks_completed_total": "Counter",
    "agent_tasks_failed_total": "Counter",
    "mcp_server_connections": "Gauge",
    "context_window_utilization": "Gauge"
}
```

---

## 10. Summary

This specification provides a complete blueprint for integrating LLM capabilities and MCP tools into the AutoDev hierarchical agent architecture:

**Key Components:**
1. **LLM Client Layer**: Abstract client interface with Anthropic implementation
2. **MCP Integration**: Standardized tool access via Model Context Protocol
3. **Tool Execution Loop**: ReAct pattern for tool-calling workflows
4. **Configuration System**: Flexible config files for deployment
5. **Testing Framework**: Comprehensive unit and integration tests
6. **Observability**: Structured logging and metrics

**Benefits:**
- **Standardization**: MCP provides unified tool interface
- **Flexibility**: Easy to swap LLM providers or add new tools
- **Reliability**: Robust error handling and retry mechanisms
- **Efficiency**: Prompt caching and parallel execution
- **Observability**: Full visibility into agent operations

**Next Steps:**
1. Implement core LLM client classes (Phase 2A)
2. Integrate MCP client and servers (Phase 2B)
3. Build tool execution loop (Phase 2C)
4. Update agent implementations (Phase 2D)
5. Test and document (Phase 2E)

This design transforms the Phase 1 scaffold into a fully functional autonomous development system capable of understanding requirements, generating code, and ensuring quality through an integrated LLM+MCP architecture.
