# AD020: Hierarchical Agent Architecture Implementation

**Status**: In Planning  
**Priority**: Critical (Force Multiplier)  
**Created**: 2026-03-22  
**Target**: 2026-04-30

---

## Overview

Implement the Manager-Coder-Reviewer hierarchical agent pattern for AutoDev. This is the strategic priority to enable AutoDev as a force multiplier across all Hermes-managed projects.

Full specification: `~/Documents/Obsidian/Hermes/Knowledge/AutoDev/Hierarchical_Architecture_Spec.md`

---

## Implementation Phases

### Phase 1: Core Agent Framework (Week 1-2)

**Files to Create:**
```
autodev/hierarchical/
├── __init__.py
├── base.py              # Base agent class
├── manager.py           # ManagerAgent implementation
├── coder.py             # CoderAgent implementation
├── reviewer.py          # ReviewerAgent implementation
├── states.py            # State machine definitions
└── communication.py     # Inter-agent messaging
```

**Tasks:**
- [ ] Create `autodev/hierarchical/` directory structure
- [ ] Implement `BaseAgent` class with MCP client connection
- [ ] Implement `ManagerAgent` with state machine (INIT → DECOMPOSE → DISPATCH → MONITOR → SYNTHESIZE → COMPLETE)
- [ ] Implement `CoderAgent` extending existing local_loop functionality
- [ ] Implement `ReviewerAgent` extending existing review_round.py
- [ ] Define `AgentMessage` protocol for inter-agent communication
- [ ] Add task assignment and result formats

### Phase 2: MCP Integration (Week 2-3)

**Files to Create:**
```
autodev/mcp/
├── __init__.py
├── client.py            # MCP client implementation
├── terminal_server.py   # Custom terminal MCP server
├── testing_server.py    # Custom testing MCP server
└── config.py            # Configuration management
```

**Tasks:**
- [ ] Create `autodev/mcp/` directory structure
- [ ] Implement `AutoDevMCPClient` class
- [ ] Create MCP configuration loader
- [ ] Implement custom terminal MCP server
- [ ] Implement custom testing MCP server
- [ ] Test connectivity with official MCP servers (filesystem, git)

### Phase 3: Hermes Integration (Week 3-4)

**Files to Create:**
```
hermes-agent/tools/
└── autodev_tool.py      # Hermes tool registration
```

**Tasks:**
- [ ] Create `autodev_tool.py` in Hermes tools directory
- [ ] Register `autodev_task` tool in Hermes registry
- [ ] Register `autodev_status` tool in Hermes registry
- [ ] Implement task handler with async execution
- [ ] Implement status monitoring
- [ ] Test Hermes → AutoDev integration end-to-end

### Phase 4: Testing & Validation (Week 4-5)

**Tasks:**
- [ ] Unit tests for each agent class
- [ ] Integration tests for Manager → Worker communication
- [ ] Integration tests for MCP layer
- [ ] Integration tests for Hermes tool
- [ ] SWE-bench benchmark runs (target: 20%+)
- [ ] Performance optimization if needed

---

## Dependencies

| Dependency | Status | Notes |
|------------|--------|-------|
| MCP Python SDK | Available | `pip install mcp` |
| Hermes Agent | Active | In ~/Projects/hermes-agent |
| Existing review_round.py | Available | Can extend for ReviewerAgent |
| Existing local_loop.py | Available | Can adapt for CoderAgent |

---

## Key Integration Points

### 1. Hermes Tool Registration

```python
# hermes-agent/tools/autodev_tool.py
registry.register(
    name="autodev_task",
    toolset="autodev",
    schema={...},
    handler=autodev_task_handler,
    is_async=True,
    description="Execute development task with hierarchical agents",
    emoji="🤖"
)
```

### 2. MCP Configuration

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["@modelcontextprotocol/server-filesystem", "${workspaceRoot}"]
    },
    "git": {
      "command": "npx",
      "args": ["@modelcontextprotocol/server-git", "--repository", "${workspaceRoot}"]
    }
  }
}
```

### 3. ManagerAgent Entry Point

```python
manager = ManagerAgent(
    mcp_config_path="~/.config/autodev/mcp_config.json",
    repo_root="."
)
result = await manager.execute_task(spec)
```

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| SWE-bench resolution | 20%+ | Benchmark runs |
| Task completion time | < 5 min avg | Timing logs |
| Review catch rate | 90%+ | Manual review |
| Hermes integration | Working | End-to-end test |

---

## Related Files

- **Full Spec**: `~/Documents/Obsidian/Hermes/Knowledge/AutoDev/Hierarchical_Architecture_Spec.md`
- **Research Index**: `~/Documents/Obsidian/Hermes/Knowledge/AutoDev/INDEX.md`
- **Existing Review**: `~/Projects/autodev/tools/auto_prd/review_round.py`
- **Existing Loop**: `~/Projects/autodev/tools/auto_prd/local_loop.py`

---

## Notes

- This is the highest-leverage investment in the Hermes ecosystem
- Each improvement here accelerates ALL other projects
- Strategic priority from mission control review (2026-03-22)
