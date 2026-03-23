"""
Tool Execution Loop

Implements the ReAct pattern for agent tool execution:
1. Agent receives task
2. Agent decides to use tool
3. Tool is executed via MCP
4. Result is fed back to agent
5. Loop continues until task complete

As specified in Section 3.1 of the Phase 2 LLM/MCP Integration Specification.
"""

from typing import List, Dict, Any, Optional, Callable
import asyncio
import logging
import time

# Import LLM types (with fallback for standalone use)
try:
    from ..llm.base_client import (
        ChatMessage,
        MessageRole,
        ToolUse,
        LLMResponse,
    )
except ImportError:
    try:
        from llm.base_client import (
            ChatMessage,
            MessageRole,
            ToolUse,
            LLMResponse,
        )
    except ImportError:
        ChatMessage = None
        MessageRole = None
        ToolUse = None
        LLMResponse = None

# Import MCP client (with fallback to mock)
try:
    from ..mcp.client import AutoDevMCPClient
    MCP_CLIENT_AVAILABLE = True
except ImportError:
    try:
        from mcp.client import AutoDevMCPClient
        MCP_CLIENT_AVAILABLE = True
    except ImportError:
        MCP_CLIENT_AVAILABLE = False
        AutoDevMCPClient = None

logger = logging.getLogger(__name__)


class ToolExecutionLoop:
    """
    Manages the tool execution loop for agents.
    
    Implements the ReAct (Reasoning + Acting) pattern:
    1. Agent receives task
    2. Agent decides to use tool
    3. Tool is executed via MCP
    4. Result is fed back to agent
    5. Loop continues until task complete or max iterations
    
    Features:
    - Configurable maximum iterations
    - Tool call callbacks for monitoring
    - Error handling and recovery
    - Parallel tool execution support
    - Detailed logging
    
    Example:
        >>> loop = ToolExecutionLoop(llm_client, mcp_client, max_iterations=20)
        >>> result = await loop.execute_with_tools(
        ...     messages=[ChatMessage(role=MessageRole.USER, content="Create a file")],
        ...     system_prompt="You are a helpful assistant."
        ... )
    """
    
    def __init__(
        self,
        llm_client,
        mcp_client,
        max_iterations: int = 20,
        enable_parallel_execution: bool = False
    ):
        """
        Initialize tool execution loop.
        
        Args:
            llm_client: LLM client for completions
            mcp_client: MCP client for tool execution
            max_iterations: Maximum tool calling iterations
            enable_parallel_execution: Enable parallel tool execution
        """
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        self.max_iterations = max_iterations
        self.enable_parallel_execution = enable_parallel_execution
        self._iteration_count = 0
        self._tools_called: List[Dict[str, Any]] = []
    
    async def execute_with_tools(
        self,
        initial_messages: List[ChatMessage],
        system_prompt: str,
        tools: Optional[List] = None,
        on_tool_call: Optional[Callable[[str, Dict], None]] = None,
        on_iteration: Optional[Callable[[int, LLMResponse], None]] = None
    ) -> str:
        """
        Execute agent task with tool calling loop.
        
        Args:
            initial_messages: Initial conversation
            system_prompt: System prompt for agent
            tools: Optional list of tools (if None, uses MCP client tools)
            on_tool_call: Optional callback for tool calls (name, input)
            on_iteration: Optional callback after each iteration
            
        Returns:
            Final response from agent
        """
        messages = list(initial_messages)
        
        # Get tools from MCP client if not provided
        if tools is None and hasattr(self.mcp_client, 'get_tools_for_llm'):
            tools = self.mcp_client.get_tools_for_llm()
        
        self._iteration_count = 0
        self._tools_called = []
        
        logger.info(f"Starting tool execution loop (max iterations: {self.max_iterations})")
        
        while self._iteration_count < self.max_iterations:
            self._iteration_count += 1
            logger.debug(f"Tool execution iteration {self._iteration_count}")
            
            try:
                # Get LLM response
                response = await self.llm_client.complete(
                    messages=messages,
                    tools=tools,
                    system_prompt=system_prompt
                )
                
                # Callback for iteration
                if on_iteration:
                    on_iteration(self._iteration_count, response)
                
                # Check if done (no tool calls or end turn)
                if not response.has_tool_calls():
                    logger.info(
                        f"Task completed after {self._iteration_count} iterations "
                        f"(stop_reason: {response.stop_reason})"
                    )
                    return response.content
                
                # Process tool calls
                if response.tool_uses:
                    # Add assistant message with tool use
                    messages.append(ChatMessage(
                        role=MessageRole.ASSISTANT,
                        content=response.content,
                        metadata={
                            "tool_uses": [t.to_dict() for t in response.tool_uses]
                        }
                    ))
                    
                    # Execute tools
                    if self.enable_parallel_execution and len(response.tool_uses) > 1:
                        tool_results = await self._execute_tools_parallel(
                            response.tool_uses,
                            on_tool_call
                        )
                    else:
                        tool_results = await self._execute_tools_sequential(
                            response.tool_uses,
                            messages,
                            on_tool_call
                        )
                        # Sequential execution already adds messages
                        continue
                    
                    # Add tool results to messages (for parallel execution)
                    for tool_use, result in zip(response.tool_uses, tool_results):
                        messages.append(ChatMessage(
                            role=MessageRole.USER,
                            content=str(result),
                            metadata={
                                "tool_result": True,
                                "tool_use_id": tool_use.id,
                            }
                        ))
                
            except Exception as e:
                logger.error(f"Error in tool execution loop: {e}")
                # Add error message and continue
                messages.append(ChatMessage(
                    role=MessageRole.USER,
                    content=f"An error occurred: {str(e)}. Please try again or use a different approach."
                ))
        
        logger.warning(f"Reached max iterations ({self.max_iterations})")
        return "Task did not complete within maximum iterations. Please try breaking down the task into smaller steps."
    
    async def _execute_tools_sequential(
        self,
        tool_uses: List[ToolUse],
        messages: List[ChatMessage],
        on_tool_call: Optional[Callable]
    ) -> None:
        """
        Execute tools sequentially, adding results to messages.
        
        Args:
            tool_uses: List of tool use requests
            messages: Conversation messages (modified in place)
            on_tool_call: Optional callback for tool calls
        """
        for tool_use in tool_uses:
            try:
                # Callback for logging/monitoring
                if on_tool_call:
                    on_tool_call(tool_use.name, tool_use.input)
                
                # Record tool call
                self._tools_called.append({
                    "name": tool_use.name,
                    "input": tool_use.input,
                    "timestamp": time.time(),
                })
                
                logger.info(f"Executing tool: {tool_use.name}")
                
                # Execute tool via MCP
                result = await self._call_tool(tool_use.name, tool_use.input)
                
                # Add tool result to messages
                messages.append(ChatMessage(
                    role=MessageRole.USER,
                    content=f"Tool {tool_use.name} result: {result}",
                    metadata={
                        "tool_result": True,
                        "tool_use_id": tool_use.id,
                        "tool_name": tool_use.name,
                    }
                ))
                
                logger.info(f"Tool {tool_use.name} executed successfully")
                
            except Exception as e:
                error_msg = f"Tool {tool_use.name} failed: {str(e)}"
                logger.error(error_msg)
                
                # Record failed tool call
                self._tools_called[-1]["error"] = str(e)
                
                messages.append(ChatMessage(
                    role=MessageRole.USER,
                    content=error_msg,
                    metadata={
                        "tool_result": True,
                        "tool_use_id": tool_use.id,
                        "tool_name": tool_use.name,
                        "is_error": True,
                    }
                ))
    
    async def _execute_tools_parallel(
        self,
        tool_uses: List[ToolUse],
        on_tool_call: Optional[Callable]
    ) -> List[Any]:
        """
        Execute multiple tools in parallel.
        
        Args:
            tool_uses: List of tool use requests
            on_tool_call: Optional callback for tool calls
            
        Returns:
            List of tool results
        """
        async def execute_single(tool_use: ToolUse) -> Any:
            if on_tool_call:
                on_tool_call(tool_use.name, tool_use.input)
            
            self._tools_called.append({
                "name": tool_use.name,
                "input": tool_use.input,
                "timestamp": time.time(),
            })
            
            logger.info(f"Executing tool (parallel): {tool_use.name}")
            return await self._call_tool(tool_use.name, tool_use.input)
        
        tasks = [execute_single(tc) for tc in tool_uses]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results, converting exceptions to error strings
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                error_msg = f"Tool {tool_uses[i].name} failed: {str(result)}"
                logger.error(error_msg)
                self._tools_called[-(len(results) - i)]["error"] = str(result)
                processed_results.append(error_msg)
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def _call_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Any:
        """
        Call a tool via the MCP client.
        
        Args:
            tool_name: Name of the tool
            tool_input: Tool input parameters
            
        Returns:
            Tool result
        """
        if self.mcp_client is None:
            raise RuntimeError("MCP client not initialized")
        
        if hasattr(self.mcp_client, 'call_tool'):
            return await self.mcp_client.call_tool(tool_name, tool_input)
        else:
            raise RuntimeError("MCP client does not support call_tool method")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get execution statistics.
        
        Returns:
            Dictionary with execution statistics
        """
        return {
            "iterations": self._iteration_count,
            "tools_called": len(self._tools_called),
            "tool_calls": self._tools_called,
            "max_iterations": self.max_iterations,
        }
    
    def reset(self) -> None:
        """Reset execution state."""
        self._iteration_count = 0
        self._tools_called = []


class MockMCPClient:
    """
    Mock MCP client for testing without actual MCP servers.
    
    Provides simulated tool responses for development and testing.
    """
    
    def __init__(self):
        self.tools = {}
        self._setup_mock_tools()
    
    def _setup_mock_tools(self):
        """Set up mock tool definitions."""
        self.tool_definitions = [
            {
                "name": "read_file",
                "description": "Read file contents",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "write_file",
                "description": "Write content to file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                        "content": {"type": "string", "description": "File content"}
                    },
                    "required": ["path", "content"]
                }
            },
            {
                "name": "execute_command",
                "description": "Execute a shell command",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Command to execute"}
                    },
                    "required": ["command"]
                }
            },
        ]
    
    def get_tools_for_llm(self):
        """Get mock tool definitions."""
        from ..llm.base_client import ToolDefinition
        return [
            ToolDefinition(
                name=t["name"],
                description=t["description"],
                input_schema=t["input_schema"],
                mcp_server="mock"
            )
            for t in self.tool_definitions
        ]
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Simulate tool execution."""
        logger.info(f"Mock MCP: {tool_name} called with {arguments}")
        
        if tool_name == "read_file":
            return f"[Mock file content from {arguments.get('path', 'unknown')}]"
        elif tool_name == "write_file":
            return f"[Mock: wrote {len(arguments.get('content', ''))} bytes to {arguments.get('path', 'unknown')}]"
        elif tool_name == "execute_command":
            return f"[Mock: executed '{arguments.get('command', '')}']"
        else:
            return f"[Mock: unknown tool {tool_name}]"
    
    async def connect_all(self):
        """Mock connection."""
        logger.info("Mock MCP: Connected")
    
    async def disconnect_all(self):
        """Mock disconnection."""
        logger.info("Mock MCP: Disconnected")
