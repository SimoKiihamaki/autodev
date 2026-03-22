# AutoDev Phase 2 - Documentation

This directory contains all documentation for Phase 2: LLM/MCP Integration.

## Quick Navigation

### Start Here
1. **[Executive Summary](phase2_executive_summary.md)** - High-level overview and outcomes
2. **[Main Specification](phase2_llm_mcp_integration_spec.md)** - Complete technical specification
3. **[Implementation Checklist](phase2_implementation_checklist.md)** - 5-week roadmap

### Reference
- **[Quick Reference Guide](phase2_quick_reference.md)** - Common patterns and code snippets
- **[Usage Examples](../examples/phase2_usage_example.py)** - Working code examples

### Configuration
- **[Main Config Template](../config/config.template.json)** - LLM and agent settings
- **[MCP Config Template](../config/mcp_config.template.json)** - MCP server settings

## Document Overview

### 1. Executive Summary
**File:** `phase2_executive_summary.md`  
**Purpose:** High-level overview for stakeholders  
**Contents:**
- Objectives and accomplishments
- Technical architecture
- Design decisions
- Implementation roadmap
- Expected outcomes
- Risk mitigation

**Read this if:** You want to understand what Phase 2 delivers and why

### 2. Main Specification
**File:** `phase2_llm_mcp_integration_spec.md`  
**Purpose:** Complete technical specification  
**Contents:**
- LLM client architecture and interfaces
- MCP client implementation details
- Tool execution loop design
- Agent integration patterns
- Configuration system
- Testing strategy
- Performance optimization
- Security considerations
- Monitoring approach

**Read this if:** You're implementing or reviewing the code

### 3. Implementation Checklist
**File:** `phase2_implementation_checklist.md`  
**Purpose:** Track implementation progress  
**Contents:**
- Week-by-week breakdown (Phase 2A through 2E)
- 150+ actionable tasks
- Dependencies between tasks
- Testing requirements
- Documentation needs
- Success criteria

**Read this if:** You're implementing Phase 2

### 4. Quick Reference Guide
**File:** `phase2_quick_reference.md`  
**Purpose:** Fast lookup for common patterns  
**Contents:**
- LLM client quick start
- MCP client quick start
- Agent quick start
- Common patterns
- Configuration snippets
- Troubleshooting tips

**Read this if:** You need a quick code example or solution

## Implementation Roadmap

### Week 1: Core LLM Integration (Phase 2A)
- Base LLM client interfaces
- Anthropic client implementation
- System prompts
- Unit tests

**Deliverable:** Working LLM client

### Week 2: MCP Integration (Phase 2B)
- MCP client implementation
- Server configuration
- Tool discovery
- Integration tests

**Deliverable:** Connected to MCP servers

### Week 3: Tool Execution Loop (Phase 2C)
- ReAct pattern implementation
- Base agent updates
- Error handling

**Deliverable:** Agents can call tools

### Week 4: Agent Updates (Phase 2D)
- Manager task decomposition
- Coder feature implementation
- Reviewer code analysis

**Deliverable:** Full workflow operational

### Week 5: Testing & Documentation (Phase 2E)
- Comprehensive tests
- API documentation
- Performance benchmarks

**Deliverable:** Production-ready

## Configuration Files

### Main Configuration
**File:** `config/config.template.json`  
**Sections:**
- `llm`: LLM provider settings (Anthropic)
- `mcp`: MCP connection settings
- `agents`: Per-agent configurations
- `logging`: Logging settings
- `security`: Security constraints
- `performance`: Optimization settings

**Usage:** Copy to `~/.config/autodev/config.json` and customize

### MCP Server Configuration
**File:** `config/mcp_config.template.json`  
**Sections:**
- `servers`: List of MCP servers to connect
  - filesystem: File operations
  - git: Version control
  - terminal: Command execution
  - github: GitHub API (optional)
  - postgres: Database access (optional)
- `security`: Allowed paths and commands
- `connection_settings`: Timeout and retry

**Usage:** Copy to `~/.config/autodev/mcp_config.json` and customize

## Examples

### Usage Examples
**File:** `examples/phase2_usage_example.py`  
**Examples:**
1. Simple feature implementation
2. Coder with tools
3. Reviewer workflow
4. Direct MCP client usage
5. Custom LLM configuration

**Run with:**
```bash
python examples/phase2_usage_example.py
```

## Dependencies

### Required
```
anthropic>=0.40.0        # Anthropic Claude API
mcp>=0.9.0               # Model Context Protocol SDK
asyncio-compat>=0.1.0    # Async compatibility
pydantic>=2.0.0          # Data validation
python-dotenv>=1.0.0     # Environment variables
```

### Development
```
pytest>=8.0.0            # Testing framework
pytest-asyncio>=0.23.0   # Async test support
black>=24.0.0            # Code formatter
mypy>=1.8.0              # Type checker
```

### MCP Servers
```bash
# Install filesystem server
npm install -g @modelcontextprotocol/server-filesystem

# Install git server
npm install -g @modelcontextprotocol/server-git

# Install terminal server
npm install -g @modelcontextprotocol/server-terminal
```

## Environment Setup

### Required Variables
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Optional Variables
```bash
export AUTODEV_DEFAULT_MODEL="claude-3-5-sonnet-20241022"
export AUTODEV_LOG_LEVEL="DEBUG"
```

## Testing

### Run Unit Tests
```bash
pytest tests/llm/ -v
pytest tests/mcp/ -v
pytest tests/agents/ -v
```

### Run Integration Tests
```bash
pytest tests/integration/ -v --integration
```

### Check Coverage
```bash
pytest --cov=autodev --cov-report=html
```

## Architecture Overview

```
┌─────────────────────────────────────────────┐
│              USER TASK                      │
└────────────────┬────────────────────────────┘
                 │
┌────────────────▼────────────────────────────┐
│          MANAGER AGENT                      │
│  - Decompose task                           │
│  - Assign to workers                        │
│  - Monitor progress                         │
│  - Synthesize results                       │
└────────┬───────────────────────────────────┘
         │
    ┌────┴─────┬──────────┐
    │          │          │
┌───▼────┐ ┌───▼─────┐ ┌──▼──────┐
│ CODER  │ │REVIEWER │ │ TESTER  │
│ AGENT  │ │  AGENT  │ │  AGENT  │
└───┬────┘ └───┬─────┘ └──┬──────┘
    │          │          │
    └──────────┴──────────┘
               │
      ┌────────▼────────┐
      │  LLM CLIENT     │  Anthropic Claude
      │  (Anthropic)    │  - Task reasoning
      └────────┬────────┘  - Code generation
               │           - Decision making
      ┌────────▼────────┐
      │  MCP CLIENT     │  Model Context Protocol
      │                 │  - Filesystem tools
      └────────┬────────┘  - Git operations
               │           - Terminal commands
      ┌────────▼────────┐
      │  MCP SERVERS    │
      │  - Filesystem   │
      │  - Git          │
      │  - Terminal     │
      └─────────────────┘
```

## Key Concepts

### LLM Integration
- **Provider Abstraction:** Support multiple LLM providers
- **Streaming:** Real-time response streaming
- **Caching:** Prompt caching for cost reduction
- **Tool Calling:** Claude's native tool use capability

### MCP Integration
- **Standardization:** Open protocol for tool access
- **Discovery:** Dynamic tool discovery from servers
- **Isolation:** Servers run in separate processes
- **Security:** Scoped access and whitelisting

### Tool Execution
- **ReAct Pattern:** Reason → Act → Observe loop
- **Automatic:** Agent decides when to use tools
- **Feedback:** Tool results inform next action
- **Limits:** Max iterations and timeouts

### Configuration
- **JSON-based:** All settings in config files
- **Templates:** Provided templates for customization
- **Validation:** Configuration validation on startup
- **Environment:** Support for env variable substitution

## Performance Targets

| Metric | Target |
|--------|--------|
| Task decomposition | 30-60 seconds |
| Feature implementation | 2-5 minutes |
| Code review | 30-60 seconds |
| Full workflow | 5-10 minutes |
| Tool call latency | <10 seconds |
| Cache hit rate | >90% |
| Test coverage | >80% |

## Cost Estimates

| Task Type | Estimated Cost |
|-----------|---------------|
| Simple feature | $0.10 - $0.50 |
| Complex feature | $0.50 - $2.00 |
| Large refactor | $2.00 - $5.00 |
| Full project | TBD |

*Costs assume prompt caching enabled*

## Troubleshooting

### LLM Issues
- **API key error:** Set ANTHROPIC_API_KEY environment variable
- **Rate limit:** Implement retry with exponential backoff
- **High costs:** Enable prompt caching, reduce max_tokens

### MCP Issues
- **Server not found:** Install MCP server (npm install -g)
- **Permission denied:** Check allowed_paths in config
- **Timeout:** Increase connection_timeout_seconds

### Agent Issues
- **Not initializing:** Call await agent.initialize()
- **Tool not found:** Check MCP server is enabled
- **Infinite loop:** Check max_iterations setting

## Support

### Documentation
- Check quick reference for common patterns
- Review examples for usage demonstrations
- Consult main spec for implementation details

### Logging
- Enable DEBUG logging for detailed output
- Check logs at ~/.local/share/autodev/logs/
- Review audit log for security events

### Community
- MCP GitHub: https://github.com/modelcontextprotocol
- Anthropic Docs: https://docs.anthropic.com/

---

**Last Updated:** March 23, 2026  
**Phase:** 2 - LLM/MCP Integration  
**Status:** Documentation Complete ✅
