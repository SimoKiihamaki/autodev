# AutoDev Integration Layer

This module provides the Phase 5 integration between the LLM client and MCP client, enabling autonomous software development through the ReAct (Reasoning + Acting) pattern.

## Quick Start

```python
from integration import AutoDevPipeline, PipelineConfig
from llm.base_client import LLMConfig

# Configure
config = PipelineConfig(
    llm_config=LLMConfig(api_key="your-api-key"),
    max_tool_iterations=20
)

# Execute
async with AutoDevPipeline(config) as pipeline:
    result = await pipeline.execute_task(
        "Create a Python function that calculates fibonacci numbers"
    )
    print(result.content)
```

## Components

### Core Classes

- **`AutoDevPipeline`** - Main integration class connecting LLM and MCP
- **`CoderPipeline`** - Specialized pipeline for coding tasks
- **`PipelineConfig`** - Configuration options
- **`ExecutionResult`** - Task execution result structure

### Convenience Functions

- **`quick_code(task, api_key, workspace)`** - One-off coding task
- **`create_coder_pipeline(api_key, workspace, max_iterations)`** - Create configured pipeline

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     AutoDev Pipeline                         │
│                                                              │
│  ┌──────────────┐      ┌──────────────┐      ┌───────────┐ │
│  │  LLM Client  │◄────►│  Tool        │◄────►│MCP Client │ │
│  │  (Claude)    │      │  Executor    │      │           │ │
│  └──────────────┘      └──────────────┘      └───────────┘ │
│         │                      │                    │        │
│         ▼                      ▼                    ▼        │
│  ┌──────────────┐      ┌──────────────┐      ┌───────────┐ │
│  │   Reasoning  │      │   Tool       │      │  MCP      │ │
│  │   & Planning │      │   Selection  │      │  Servers  │ │
│  └──────────────┘      └──────────────┘      └───────────┘ │
└──────────────────────────────────────────────────────────────┘
```

## Files

- **`integration.py`** - Main integration layer
- **`llm/client.py`** - LLM client (Phase 3)
- **`mcp/client.py`** - MCP client (Phase 4)
- **`agents/tool_executor.py`** - ReAct loop implementation
- **`agents/base.py`** - Base agent class

## Tests

```bash
# Mock mode (no API key needed)
python test_phase5_mock.py

# Real API mode
export ANTHROPIC_API_KEY="your-key"
python test_phase5_integration.py
```

## Documentation

See [docs/phase5_integration_guide.md](../docs/phase5_integration_guide.md) for comprehensive documentation.
