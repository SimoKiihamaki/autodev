"""
AutoDev Integration Layer - Phase 5

Connects the LLM client and MCP client to enable autonomous coding workflows.
This module provides the integration layer that ties together:
- LLM Client for intelligent reasoning
- MCP Client for tool execution
- ReAct loop for iterative problem solving

Usage:
    from integration import AutoDevPipeline
    
    async def main():
        pipeline = AutoDevPipeline()
        await pipeline.initialize()
        result = await pipeline.execute_task("Create a simple hello world Python script")
        print(result)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
import json
import os

# Import LLM components
try:
    from llm.client import LLMClient, LLMConfig
    from llm.base_client import ChatMessage, MessageRole, ToolDefinition, LLMResponse
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    LLMClient = None
    LLMConfig = None

# Import MCP components
try:
    from mcp.client import AutoDevMCPClient, MCPServerConfig, MCPSecurityConfig
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    AutoDevMCPClient = None

# Import tool executor
try:
    from agents.tool_executor import ToolExecutionLoop
    TOOL_EXECUTOR_AVAILABLE = True
except ImportError:
    TOOL_EXECUTOR_AVAILABLE = False
    ToolExecutionLoop = None

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for the AutoDev pipeline."""
    llm_config: Optional[Any] = None
    mcp_config_path: str = "~/.config/autodev/mcp_config.json"
    max_tool_iterations: int = 20
    enable_parallel_tools: bool = False
    security_config: Optional[Any] = None
    workspace_path: str = "."
    enable_logging: bool = True
    log_level: str = "INFO"


@dataclass
class ExecutionResult:
    """Result of pipeline execution."""
    success: bool
    content: str
    files_modified: List[str] = field(default_factory=list)
    tools_called: List[Dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    tokens_used: Dict[str, int] = field(default_factory=dict)
    execution_time_seconds: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class AutoDevPipeline:
    """
    Main integration pipeline connecting LLM and MCP for autonomous coding.
    
    This class orchestrates:
    1. LLM client for intelligent reasoning
    2. MCP client for tool execution (filesystem, git, terminal, etc.)
    3. ReAct loop for iterative problem solving
    
    Example:
        >>> pipeline = AutoDevPipeline()
        >>> await pipeline.initialize()
        >>> result = await pipeline.execute_task("Create a Python function that calculates fibonacci")
        >>> print(result.content)
    """
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        """
        Initialize the pipeline.
        
        Args:
            config: Pipeline configuration (uses defaults if not provided)
        """
        self.config = config or PipelineConfig()
        
        # Initialize clients
        self._llm_client: Optional[LLMClient] = None
        self._mcp_client: Optional[AutoDevMCPClient] = None
        self._tool_executor: Optional[ToolExecutionLoop] = None
        
        # State
        self._initialized = False
        self._workspace_path = Path(self.config.workspace_path).resolve()
        
        # Logging
        if self.config.enable_logging:
            logging.basicConfig(
                level=getattr(logging, self.config.log_level.upper()),
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
    
    async def initialize(self) -> None:
        """
        Initialize all pipeline components.
        
        This method:
        1. Initializes the LLM client
        2. Connects to MCP servers
        3. Sets up the tool execution loop
        
        Raises:
            RuntimeError: If initialization fails
        """
        logger.info("Initializing AutoDev pipeline...")
        
        try:
            # Initialize LLM client
            await self._initialize_llm()
            logger.info("✓ LLM client initialized")
            
            # Initialize MCP client
            await self._initialize_mcp()
            logger.info("✓ MCP client initialized")
            
            # Initialize tool executor
            await self._initialize_tool_executor()
            logger.info("✓ Tool executor initialized")
            
            self._initialized = True
            logger.info("AutoDev pipeline ready")
            
        except Exception as e:
            logger.error(f"Pipeline initialization failed: {e}")
            raise RuntimeError(f"Failed to initialize pipeline: {e}")
    
    async def _initialize_llm(self) -> None:
        """Initialize the LLM client."""
        if not LLM_AVAILABLE:
            raise RuntimeError("LLM modules not available. Please install dependencies.")
        
        llm_config = self.config.llm_config or LLMConfig()
        
        # Ensure API key is set
        if not llm_config.api_key:
            llm_config.api_key = os.environ.get("ANTHROPIC_API_KEY")
        
        if not llm_config.api_key:
            raise RuntimeError(
                "No API key provided. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key in LLMConfig."
            )
        
        self._llm_client = LLMClient(llm_config)
    
    async def _initialize_mcp(self) -> None:
        """Initialize the MCP client."""
        if not MCP_AVAILABLE:
            logger.warning("MCP package not available. Using mock tools.")
            from agents.tool_executor import MockMCPClient
            self._mcp_client = MockMCPClient()
            await self._mcp_client.connect_all()
            return
        
        security_config = self.config.security_config or MCPSecurityConfig(
            allowed_paths=[str(self._workspace_path)],
            allow_all_paths=True,  # For development
            allow_all_commands=True,  # For development
        )
        
        self._mcp_client = AutoDevMCPClient(
            config_path=self.config.mcp_config_path,
            security_config=security_config
        )
        
        await self._mcp_client.connect_all()
    
    async def _initialize_tool_executor(self) -> None:
        """Initialize the tool execution loop."""
        if not TOOL_EXECUTOR_AVAILABLE:
            raise RuntimeError("Tool executor not available")
        
        if not self._llm_client or not self._mcp_client:
            raise RuntimeError("LLM and MCP clients must be initialized first")
        
        self._tool_executor = ToolExecutionLoop(
            llm_client=self._llm_client,
            mcp_client=self._mcp_client,
            max_iterations=self.config.max_tool_iterations,
            enable_parallel_execution=self.config.enable_parallel_tools
        )
    
    async def execute_task(
        self,
        task: str,
        system_prompt: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        on_tool_call: Optional[Callable[[str, Dict], None]] = None,
        on_iteration: Optional[Callable[[int, Any], None]] = None
    ) -> ExecutionResult:
        """
        Execute a coding task using the integrated LLM + MCP pipeline.
        
        This method implements the ReAct pattern:
        1. LLM analyzes the task
        2. LLM decides which tools to use (if any)
        3. Tools are executed via MCP
        4. Results are fed back to LLM
        5. Loop continues until task is complete
        
        Args:
            task: Task description (e.g., "Create a hello world script")
            system_prompt: Optional custom system prompt
            context: Additional context (files, requirements, etc.)
            on_tool_call: Callback for tool call events
            on_iteration: Callback for iteration events
            
        Returns:
            ExecutionResult with task outcome
        """
        if not self._initialized:
            raise RuntimeError("Pipeline not initialized. Call initialize() first.")
        
        start_time = datetime.utcnow()
        
        logger.info(f"Executing task: {task[:100]}...")
        
        try:
            # Build initial message
            initial_message = self._build_task_message(task, context)
            messages = [initial_message]
            
            # Get system prompt
            system = system_prompt or self._get_default_system_prompt()
            
            # Execute with tool loop
            content = await self._tool_executor.execute_with_tools(
                initial_messages=messages,
                system_prompt=system,
                on_tool_call=on_tool_call,
                on_iteration=on_iteration
            )
            
            # Get execution stats
            stats = self._tool_executor.get_stats()
            llm_stats = self._llm_client.get_usage_stats()
            
            # Build result
            end_time = datetime.utcnow()
            execution_time = (end_time - start_time).total_seconds()
            
            result = ExecutionResult(
                success=True,
                content=content,
                tools_called=stats.get("tool_calls", []),
                iterations=stats.get("iterations", 0),
                tokens_used={
                    "total_tokens": llm_stats.get("total_tokens", 0),
                    "input_tokens": llm_stats.get("input_tokens", 0),
                    "output_tokens": llm_stats.get("output_tokens", 0),
                },
                execution_time_seconds=execution_time,
                metadata={
                    "max_iterations": self.config.max_tool_iterations,
                    "workspace": str(self._workspace_path),
                }
            )
            
            logger.info(
                f"Task completed in {execution_time:.2f}s "
                f"({result.iterations} iterations, {len(result.tools_called)} tool calls)"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            return ExecutionResult(
                success=False,
                content="",
                error=str(e),
                metadata={"exception_type": type(e).__name__}
            )
    
    def _build_task_message(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ChatMessage:
        """Build the initial task message with context."""
        content = task
        
        if context:
            # Add context information
            context_parts = []
            
            if "files" in context:
                context_parts.append(f"Relevant files: {', '.join(context['files'])}")
            
            if "requirements" in context:
                context_parts.append(f"Requirements: {context['requirements']}")
            
            if "constraints" in context:
                context_parts.append(f"Constraints: {context['constraints']}")
            
            if context_parts:
                content = f"{task}\n\nContext:\n" + "\n".join(context_parts)
        
        return ChatMessage(role=MessageRole.USER, content=content)
    
    def _get_default_system_prompt(self) -> str:
        """Get the default system prompt for coding tasks."""
        return """You are an expert software developer with access to tools for file operations, command execution, and version control.

Your capabilities:
- Read and write files
- Execute shell commands
- Work with git repositories
- Create, modify, and test code

When working on tasks:
1. First, understand the requirements and constraints
2. Plan your approach before making changes
3. Use tools to read existing code and context
4. Make incremental, well-tested changes
5. Verify your work by running tests or checking output

Always:
- Write clean, well-documented code
- Follow existing code style and patterns
- Handle errors appropriately
- Test your changes when possible

You have access to the following tools through MCP servers. Use them as needed to complete tasks efficiently."""
    
    async def execute_simple_task(self, task: str) -> str:
        """
        Execute a simple task and return just the result content.
        
        Convenience method for quick tasks.
        
        Args:
            task: Task description
            
        Returns:
            Result content string
        """
        result = await self.execute_task(task)
        return result.content
    
    def get_available_tools(self) -> List[ToolDefinition]:
        """Get list of available tools from MCP servers."""
        if not self._mcp_client:
            return []
        
        if hasattr(self._mcp_client, 'get_tools_for_llm'):
            return self._mcp_client.get_tools_for_llm()
        
        return []
    
    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific tool."""
        if not self._mcp_client or not hasattr(self._mcp_client, 'tools'):
            return None
        
        tool_info = self._mcp_client.tools.get(tool_name)
        if tool_info:
            return {
                "name": tool_info.name,
                "description": tool_info.description,
                "server": tool_info.server_name,
                "input_schema": tool_info.input_schema
            }
        
        return None
    
    async def shutdown(self) -> None:
        """
        Shutdown the pipeline and release resources.
        
        This method:
        1. Disconnects from MCP servers
        2. Logs usage statistics
        3. Cleans up resources
        """
        logger.info("Shutting down AutoDev pipeline...")
        
        if self._mcp_client:
            try:
                await self._mcp_client.disconnect_all()
                logger.info("✓ MCP client disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting MCP client: {e}")
        
        if self._llm_client:
            stats = self._llm_client.get_usage_stats()
            logger.info(f"LLM usage stats: {stats}")
        
        self._initialized = False
        logger.info("Pipeline shutdown complete")
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.shutdown()


class CoderPipeline(AutoDevPipeline):
    """
    Specialized pipeline for coding tasks.
    
    Pre-configured for software development with:
    - Coding-focused system prompt
    - File operation tools
    - Test execution capabilities
    """
    
    def _get_default_system_prompt(self) -> str:
        """Get coding-focused system prompt."""
        return """You are an expert software developer agent with access to development tools.

Your primary responsibilities:
1. Write clean, efficient, and well-documented code
2. Follow existing code patterns and style guidelines
3. Implement features according to specifications
4. Fix bugs and refactor code for better quality
5. Write and run tests to verify your work

Available tools:
- File operations: read_file, write_file, list_directory, create_directory
- Command execution: execute_command (for running tests, build tools, etc.)
- Git operations: git_status, git_diff, git_commit

Best practices:
- Read existing code before making changes
- Make incremental, testable changes
- Write clear commit messages
- Handle edge cases and errors
- Document complex logic

Always verify your work by running tests or checks when possible."""


# Convenience functions

async def quick_code(
    task: str,
    api_key: Optional[str] = None,
    workspace: str = "."
) -> str:
    """
    Quick one-off coding task execution.
    
    Args:
        task: Task description
        api_key: Optional API key (uses env var if not provided)
        workspace: Workspace directory
        
    Returns:
        Result content string
        
    Example:
        >>> result = await quick_code("Create a hello world Python script")
        >>> print(result)
    """
    config = PipelineConfig(
        llm_config=LLMConfig(api_key=api_key),
        workspace_path=workspace
    )
    
    async with CoderPipeline(config) as pipeline:
        result = await pipeline.execute_task(task)
        return result.content


def create_coder_pipeline(
    api_key: Optional[str] = None,
    workspace: str = ".",
    max_iterations: int = 20
) -> CoderPipeline:
    """
    Create a pre-configured coder pipeline.
    
    Args:
        api_key: Optional API key
        workspace: Workspace directory
        max_iterations: Maximum tool calling iterations
        
    Returns:
        Configured CoderPipeline instance (not yet initialized)
        
    Example:
        >>> pipeline = create_coder_pipeline()
        >>> await pipeline.initialize()
        >>> result = await pipeline.execute_task("Write a function")
    """
    config = PipelineConfig(
        llm_config=LLMConfig(api_key=api_key),
        workspace_path=workspace,
        max_tool_iterations=max_iterations
    )
    
    return CoderPipeline(config)


# Export public API
__all__ = [
    'AutoDevPipeline',
    'CoderPipeline',
    'PipelineConfig',
    'ExecutionResult',
    'quick_code',
    'create_coder_pipeline',
]
