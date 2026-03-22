# AutoDev Phase 2 - Quick Reference Guide

## LLM Client Quick Start

### Initialize LLM Client

```python
from autodev.llm import AnthropicClient, LLMConfig, ChatMessage, MessageRole

# Create configuration
config = LLMConfig(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-5-sonnet-20241022",
    max_tokens=4096
)

# Create client
client = AnthropicClient(config)

# Make a completion
messages = [ChatMessage(role=MessageRole.USER, content="Hello!")]
response = await client.complete(messages)
print(response.content)
```

### Streaming Completion

```python
async for chunk in client.stream_complete(messages):
    print(chunk, end="", flush=True)
```

## MCP Client Quick Start

### Connect to MCP Servers

```python
from autodev.mcp import AutoDevMCPClient

# Create client
mcp_client = AutoDevMCPClient("~/.config/autodev/mcp_config.json")

# Connect to all servers
await mcp_client.connect_all()

# List available tools
tools = mcp_client.get_tools_for_llm()
print([t.name for t in tools])
```

### Call MCP Tools

```python
# Read a file
content = await mcp_client.call_tool("read_file", {"path": "main.py"})

# Write a file
await mcp_client.call_tool("write_file", {
    "path": "output.txt",
    "content": "Hello, world!"
})

# Execute command
output = await mcp_client.call_tool("execute_command", {
    "command": "pytest tests/"
})
```

## Agent Quick Start

### Initialize Agent

```python
from autodev.agents import CoderAgent
from autodev.base import TaskSpec

# Create agent
coder = CoderAgent(
    mcp_config_path="~/.config/autodev/mcp_config.json",
    repo_root="."
)

# Initialize (connects to LLM and MCP)
await coder.initialize()
```

### Execute Task

```python
# Define task
task = TaskSpec(
    task_type="implement",
    specification="Create a utility function",
    target_files=["utils.py"]
)

# Execute
result = await coder.execute(task)
print(f"Status: {result.status}")
print(f"Files: {result.files_modified}")
```

### Clean Shutdown

```python
await coder.shutdown()
```

## Manager Agent Workflow

### Full Workflow

```python
from autodev.agents import ManagerAgent

manager = ManagerAgent()
await manager.initialize()

task = TaskSpec(
    task_type="implement",
    specification="Add user authentication feature",
    target_files=["auth.py", "models.py"],
    constraints={
        "acceptance_criteria": [
            "Users can log in",
            "Passwords are hashed",
            "Sessions are managed"
        ]
    }
)

result = await manager.execute(task)

# Manager will:
# 1. Decompose task into subtasks
# 2. Dispatch to workers (Coder, Reviewer)
# 3. Monitor progress
# 4. Synthesize results

await manager.shutdown()
```

## Configuration

### Main Config File (~/.config/autodev/config.json)

```json
{
  "llm": {
    "provider": "anthropic",
    "api_key": "${ANTHROPIC_API_KEY}",
    "model": "claude-3-5-sonnet-20241022"
  },
  "mcp": {
    "config_path": "~/.config/autodev/mcp_config.json"
  }
}
```

### MCP Config File (~/.config/autodev/mcp_config.json)

```json
{
  "servers": [
    {
      "name": "filesystem",
      "command": "mcp-server-filesystem",
      "args": ["--root", "."],
      "enabled": true
    }
  ]
}
```

## Environment Variables

```bash
# Required
export ANTHROPIC_API_KEY="sk-ant-..."

# Optional
export AUTODEV_DEFAULT_MODEL="claude-3-5-sonnet-20241022"
export AUTODEV_LOG_LEVEL="DEBUG"
```

## Common Patterns

### Pattern 1: Simple Feature Implementation

```python
manager = ManagerAgent()
await manager.initialize()

result = await manager.execute(TaskSpec(
    task_type="implement",
    specification="Add feature X",
    target_files=["file.py"]
))

await manager.shutdown()
```

### Pattern 2: Code Review

```python
reviewer = ReviewerAgent(strict_mode=True)
await reviewer.initialize()

result = await reviewer.execute(TaskSpec(
    task_type="review",
    specification="Review changes in file.py",
    target_files=["file.py"]
))

print(f"Verdict: {result.review_verdict}")

await reviewer.shutdown()
```

### Pattern 3: Bug Fix

```python
coder = CoderAgent()
await coder.initialize()

result = await coder.execute(TaskSpec(
    task_type="debug",
    specification="Fix null pointer exception in UserService",
    target_files=["services/user.py"]
))

await coder.shutdown()
```

### Pattern 4: Direct MCP Tool Use

```python
mcp = AutoDevMCPClient()
await mcp.connect_all()

# Read file
code = await mcp.call_tool("read_file", {"path": "main.py"})

# Run tests
test_output = await mcp.call_tool("execute_command", {
    "command": "pytest tests/"
})

# Write result
await mcp.call_tool("write_file", {
    "path": "test_results.txt",
    "content": test_output
})

await mcp.disconnect_all()
```

## Monitoring & Debugging

### Enable Debug Logging

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### Check LLM Usage

```python
# After executing tasks
if agent._llm_client:
    stats = agent._llm_client.get_usage_stats()
    print(f"Total tokens: {stats['total_tokens']}")
    print(f"Requests: {stats['request_count']}")
```

### List MCP Tools

```python
tools = mcp_client.get_tools_for_llm()
for tool in tools:
    print(f"{tool.name}: {tool.description}")
```

## Troubleshooting

### Issue: "MCP client not initialized"

**Solution:** Call `await agent.initialize()` before executing tasks.

### Issue: "API key not found"

**Solution:** Set environment variable:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Issue: "Tool not found"

**Solution:** Check MCP server configuration and ensure server is enabled:
```python
# List available tools
tools = mcp_client.tools.keys()
print(tools)
```

### Issue: "Context window exceeded"

**Solution:** Reduce conversation history or increase max_tokens:
```python
config = LLMConfig(max_tokens=8192)
```

## Performance Tips

### 1. Enable Prompt Caching

```python
config = LLMConfig(enable_caching=True)
```

### 2. Use Appropriate Model

```python
# For complex reasoning
config.model = "claude-3-5-sonnet-20241022"

# For simple tasks
config.model = "claude-3-5-haiku-20241022"
```

### 3. Set Timeouts

```python
config = LLMConfig(timeout_seconds=180)
```

### 4. Limit Tool Calls

```python
executor = ToolExecutionLoop(max_iterations=10)
```

## Next Steps

1. Review the full specification: `docs/phase2_llm_mcp_integration_spec.md`
2. Run examples: `python examples/phase2_usage_example.py`
3. Configure your environment
4. Start implementing your agents!

## Getting Help

- Check logs: `~/.local/share/autodev/logs/autodev.log`
- Review config: `~/.config/autodev/config.json`
- Test MCP servers: `mcp-server-filesystem --help`
- Consult Anthropic docs: https://docs.anthropic.com/
