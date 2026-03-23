# AutoDev Phase 5: LLM ↔ MCP Integration

**Version:** 5.0.0  
**Created:** 2026-03-23  
**Status:** Complete  
**Depends On:** Phase 3 (LLM Client), Phase 4 (MCP Client)

---

## Executive Summary

Phase 5 completes the integration between the LLM client and MCP client, creating a unified pipeline for autonomous software development. This integration enables the ReAct (Reasoning + Acting) pattern where the LLM can reason about tasks, execute tools via MCP, and iterate based on results.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     AutoDev Pipeline                         │
│                                                              │
│  ┌──────────────┐      ┌──────────────┐      ┌───────────┐ │
│  │              │      │   Tool       │      │           │ │
│  │  LLM Client  │◄────►│  Execution   │◄────►│MCP Client │ │
│  │  (Claude)    │      │    Loop      │      │           │ │
│  └──────────────┘      └──────────────┘      └───────────┘ │
│         │                      │                    │        │
│         │                      │                    │        │
│         ▼                      ▼                    ▼        │
│  ┌──────────────┐      ┌──────────────┐      ┌───────────┐ │
│  │   Reasoning  │      │   Tool       │      │  MCP      │ │
│  │   & Planning │      │   Selection  │      │  Servers  │ │
│  └──────────────┘      └──────────────┘      └───────────┘ │
│                                                      │       │
└──────────────────────────────────────────────────────┼───────┘
                                                       │
                                        ┌──────────────┼──────────────┐
                                        │              │              │
                                        ▼              ▼              ▼
                                   ┌─────────┐  ┌─────────┐  ┌─────────┐
                                   │Filesystem│  │  Git   │  │Terminal │
                                   │  Tools  │  │  Tools │  │  Tools  │
                                   └─────────┘  └─────────┘  └─────────┘
```

---

## Components

### 1. Integration Layer (`src/integration.py`)

The main integration layer provides:

#### `AutoDevPipeline`

Main class that orchestrates LLM and MCP interaction:

```python
from integration import AutoDevPipeline, PipelineConfig
from llm.base_client import LLMConfig

# Create pipeline
config = PipelineConfig(
    llm_config=LLMConfig(api_key="your-api-key"),
    max_tool_iterations=20,
    workspace_path="/path/to/workspace"
)

pipeline = AutoDevPipeline(config)
await pipeline.initialize()

# Execute a task
result = await pipeline.execute_task(
    "Create a Python function that calculates fibonacci numbers"
)

print(result.content)
print(f"Tools called: {len(result.tools_called)}")
print(f"Iterations: {result.iterations}")

# Cleanup
await pipeline.shutdown()
```

#### `CoderPipeline`

Specialized pipeline for coding tasks:

```python
from integration import CoderPipeline, PipelineConfig

async with CoderPipeline(config) as pipeline:
    result = await pipeline.execute_task(
        "Refactor the authentication module to use async/await"
    )
    print(result.content)
```

#### `PipelineConfig`

Configuration options:

```python
@dataclass
class PipelineConfig:
    llm_config: Optional[LLMConfig] = None
    mcp_config_path: str = "~/.config/autodev/mcp_config.json"
    max_tool_iterations: int = 20
    enable_parallel_tools: bool = False
    security_config: Optional[MCPSecurityConfig] = None
    workspace_path: str = "."
    enable_logging: bool = True
    log_level: str = "INFO"
```

#### `ExecutionResult`

Result structure:

```python
@dataclass
class ExecutionResult:
    success: bool
    content: str
    files_modified: List[str]
    tools_called: List[Dict[str, Any]]
    iterations: int
    tokens_used: Dict[str, int]
    execution_time_seconds: float
    error: Optional[str]
    metadata: Dict[str, Any]
```

---

### 2. Tool Execution Loop (`src/agents/tool_executor.py`)

Implements the ReAct pattern:

```python
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
```

**Features:**
- Configurable maximum iterations
- Sequential and parallel tool execution
- Error handling and recovery
- Detailed logging and statistics

---

## Usage Examples

### Basic Usage

```python
from integration import AutoDevPipeline, PipelineConfig
from llm.base_client import LLMConfig

async def main():
    # Configure pipeline
    config = PipelineConfig(
        llm_config=LLMConfig(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            model="claude-3-5-sonnet-20241022"
        )
    )
    
    # Create and initialize
    async with AutoDevPipeline(config) as pipeline:
        # Execute a task
        result = await pipeline.execute_task(
            "Create a simple Flask web server with a /health endpoint"
        )
        
        if result.success:
            print("Task completed successfully!")
            print(result.content)
        else:
            print(f"Task failed: {result.error}")

asyncio.run(main())
```

### With Context Manager

```python
async with AutoDevPipeline(config) as pipeline:
    # Multiple tasks in sequence
    result1 = await pipeline.execute_task("Create a utils.py file")
    result2 = await pipeline.execute_task("Add a date formatting function")
    result3 = await pipeline.execute_task("Write tests for the utils")
```

### With Callbacks

```python
def on_tool_call(tool_name: str, tool_input: dict):
    print(f"Calling tool: {tool_name}")
    print(f"Input: {tool_input}")

def on_iteration(iteration: int, response):
    print(f"Iteration {iteration}: {response.stop_reason}")

result = await pipeline.execute_task(
    "Create a hello world script",
    on_tool_call=on_tool_call,
    on_iteration=on_iteration
)
```

### Convenience Functions

```python
from integration import quick_code, create_coder_pipeline

# Quick one-off task
result = await quick_code(
    "Create a Python script that downloads a file from a URL",
    workspace="/tmp/workspace"
)
print(result)

# Create a reusable pipeline
pipeline = create_coder_pipeline(
    api_key=os.environ["ANTHROPIC_API_KEY"],
    max_iterations=15
)
await pipeline.initialize()

result = await pipeline.execute_task("Implement a binary search algorithm")
await pipeline.shutdown()
```

---

## ReAct Loop Details

The ReAct (Reasoning + Acting) loop works as follows:

```
┌─────────────────────────────────────────────────────────────┐
│                    ReAct Loop                                │
│                                                              │
│  1. Task Input                                               │
│     │                                                        │
│     ▼                                                        │
│  2. LLM Reasoning ────► Plan next action                    │
│     │                                                        │
│     ▼                                                        │
│  3. Tool Selection ────► Choose appropriate tool            │
│     │                                                        │
│     ▼                                                        │
│  4. Tool Execution ────► Execute via MCP                    │
│     │                                                        │
│     ▼                                                        │
│  5. Result Analysis ──► Did tool succeed?                   │
│     │                                                        │
│     ├─ Yes ──► Continue to 6                                 │
│     │                                                        │
│     └─ No ───► Add error context, go to 2                   │
│                                                              │
│  6. Task Complete?                                           │
│     │                                                        │
│     ├─ Yes ──► Return result                                 │
│     │                                                        │
│     └─ No ───► Go to 2 for next iteration                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Example ReAct Flow

**Task:** "Create a Python script that prints the current time"

```
Iteration 1:
  LLM: "I need to create a file. I'll use write_file tool."
  Action: write_file(path="time_script.py", content="...")
  Result: "File created successfully"
  
Iteration 2:
  LLM: "File created. Let me verify it works by reading it."
  Action: read_file(path="time_script.py")
  Result: "# Script content..."
  
Iteration 3:
  LLM: "The script looks good. Let me test it."
  Action: execute_command(command="python time_script.py")
  Result: "2026-03-23 04:32:00"
  
Iteration 4:
  LLM: "Script works correctly. Task complete."
  Return: "Created time_script.py that prints the current time..."
```

---

## Tool Categories

### Filesystem Tools (from MCP filesystem server)

| Tool | Description |
|------|-------------|
| `read_file` | Read file contents |
| `write_file` | Write content to file |
| `list_directory` | List directory contents |
| `create_directory` | Create directory tree |
| `delete_file` | Delete file or directory |
| `move_file` | Move/rename file |
| `copy_file` | Copy file |

### Git Tools (from MCP git server)

| Tool | Description |
|------|-------------|
| `git_status` | Get repository status |
| `git_diff` | Get diff of changes |
| `git_log` | View commit history |
| `git_branch` | Branch operations |
| `git_commit` | Create commit |
| `git_checkout` | Checkout branch/commit |

### Terminal Tools (from MCP terminal server)

| Tool | Description |
|------|-------------|
| `execute_command` | Run shell command |
| `get_output` | Get command output |
| `kill_process` | Terminate running process |

---

## Configuration

### LLM Configuration

```python
from llm.base_client import LLMConfig

llm_config = LLMConfig(
    provider="anthropic",
    model="claude-3-5-sonnet-20241022",
    max_tokens=4096,
    temperature=0.7,
    api_key="your-api-key",
    timeout_seconds=120,
    max_retries=3,
    enable_caching=True
)
```

### MCP Configuration (`~/.config/autodev/mcp_config.json`)

```json
{
  "servers": [
    {
      "name": "filesystem",
      "command": "mcp-server-filesystem",
      "args": ["--root", "/workspace"],
      "enabled": true
    },
    {
      "name": "git",
      "command": "mcp-server-git",
      "args": [],
      "enabled": true
    },
    {
      "name": "terminal",
      "command": "mcp-server-terminal",
      "args": [],
      "enabled": true
    }
  ]
}
```

### Security Configuration

```python
from mcp.client import MCPSecurityConfig

security_config = MCPSecurityConfig(
    allowed_paths=["/workspace/project"],
    allowed_commands=["python", "pytest", "git"],
    allow_all_paths=False,
    allow_all_commands=False,
    require_confirmation=False,
    max_file_size_mb=10,
    enable_sandbox=True
)
```

---

## Error Handling

The pipeline handles errors at multiple levels:

### 1. API Errors

```python
result = await pipeline.execute_task("...")
if not result.success:
    print(f"Error: {result.error}")
    # Check metadata for more details
    print(result.metadata.get("exception_type"))
```

### 2. Tool Execution Errors

Tool errors are fed back to the LLM for recovery:

```python
# LLM receives error context and can try alternative approaches
# Example: If read_file fails, LLM might try list_directory first
```

### 3. Max Iterations

```python
config = PipelineConfig(
    max_tool_iterations=10  # Prevent infinite loops
)

# If max iterations reached:
# result.content will contain "Task did not complete within maximum iterations"
```

---

## Performance Optimization

### 1. Prompt Caching

The LLM client automatically caches system prompts:

```python
# First request: Full tokens counted
# Subsequent requests: Cache hit, reduced token usage
```

### 2. Parallel Tool Execution

```python
config = PipelineConfig(
    enable_parallel_tools=True  # Execute independent tools in parallel
)
```

### 3. Token Tracking

```python
result = await pipeline.execute_task("...")
print(f"Tokens used: {result.tokens_used}")

# Or from LLM client directly
stats = pipeline._llm_client.get_usage_stats()
print(f"Total tokens: {stats['total_tokens']}")
```

---

## Testing

Run the integration tests:

```bash
# Set API key
export ANTHROPIC_API_KEY="your-key"

# Run tests
cd /Users/simo/Projects/autodev/src
python test_phase5_integration.py
```

### Test Categories

1. **Pipeline Initialization** - Verifies all components initialize correctly
2. **Simple Task** - Tests basic task execution
3. **File Creation** - Tests file operations
4. **Context Manager** - Tests async context manager
5. **Tool Information** - Tests tool discovery
6. **Error Handling** - Tests error scenarios
7. **Coder Pipeline** - Tests specialized pipeline
8. **Convenience Functions** - Tests helper functions
9. **Execution Result** - Tests result structure

---

## Best Practices

### 1. Use Context Managers

```python
# Good: Automatic cleanup
async with AutoDevPipeline(config) as pipeline:
    result = await pipeline.execute_task(task)

# Avoid: Manual management (forgetting shutdown)
pipeline = AutoDevPipeline(config)
await pipeline.initialize()
result = await pipeline.execute_task(task)
# Forgot shutdown!
```

### 2. Configure Iteration Limits

```python
# Prevent runaway execution
config = PipelineConfig(
    max_tool_iterations=20  # Reasonable limit
)
``### 3. Set Up Security

```python
# Restrict operations to specific paths
security_config = MCPSecurityConfig(
    allowed_paths=["/safe/workspace"],
    allow_all_paths=False
)
```

### 4. Monitor Execution

```python
def on_tool_call(name, input):
    logger.info(f"Tool called: {name}")

def on_iteration(num, response):
    logger.info(f"Iteration {num}: {response.stop_reason}")

result = await pipeline.execute_task(
    task,
    on_tool_call=on_tool_call,
    on_iteration=on_iteration
)
```

### 5. Handle Results Properly

```python
result = await pipeline.execute_task(task)

if result.success:
    # Process result
    print(result.content)
    
    # Check what was modified
    for file in result.files_modified:
        print(f"Modified: {file}")
    
    # Check resource usage
    print(f"Tokens: {result.tokens_used['total_tokens']}")
    print(f"Time: {result.execution_time_seconds}s")
else:
    # Handle error
    print(f"Failed: {result.error}")
```

---

## Troubleshooting

### Issue: "MCP package not installed"

```
Solution: Install MCP package
pip install mcp
```

### Issue: "No API key provided"

```
Solution: Set environment variable or pass in config
export ANTHROPIC_API_KEY="your-key"
```

### Issue: "MCP servers not connecting"

```
Solution: Check MCP configuration file
cat ~/.config/autodev/mcp_config.json

Ensure MCP servers are installed:
npm install -g @modelcontextprotocol/server-filesystem
npm install -g @modelcontextprotocol/server-git
```

### Issue: "Max iterations reached"

```
Solution: Increase limit or break down task
config = PipelineConfig(max_tool_iterations=30)
```

---

## Future Enhancements

1. **Agent-Specific Pipelines** - Specialized pipelines for testing, reviewing, etc.
2. **Multi-Agent Coordination** - Pipeline for coordinating multiple agents
3. **Streaming Responses** - Real-time streaming of LLM responses
4. **Enhanced Security** - Sandboxed execution environments
5. **Caching Layer** - Cache tool results for repeated operations
6. **Metrics Dashboard** - Real-time monitoring of pipeline execution

---

## References

- [Phase 2 Specification](./phase2_llm_mcp_integration_spec.md) - LLM/MCP architecture
- [Phase 3 Tests](../src/test_phase3_llm.py) - LLM client tests
- [Phase 4 Tests](../src/test_phase4_mcp.py) - MCP client tests
- [MCP Documentation](https://modelcontextprotocol.io/) - MCP protocol docs
- [Anthropic API](https://docs.anthropic.com/) - Claude API docs

---

## Changelog

### v5.0.0 (2026-03-23)
- Initial Phase 5 release
- Complete LLM ↔ MCP integration
- ReAct loop implementation
- End-to-end testing
- Comprehensive documentation
