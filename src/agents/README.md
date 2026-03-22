# AutoDev Agent System

**Phase 1 Implementation Scaffold**

This directory contains the hierarchical agent architecture for AutoDev, implementing the Manager-Coder-Reviewer pattern as specified in the [Hierarchical Architecture Specification](~/Documents/Obsidian/Hermes/Knowledge/AutoDev/Hierarchical_Architecture_Spec.md).

## Structure

```
src/agents/
├── __init__.py         # Package initialization
├── base.py             # Base agent class and interfaces
├── states.py           # State machine definitions
├── communication.py    # Inter-agent messaging protocol
├── manager.py          # Manager Agent (Orchestrator)
├── coder.py            # Coder Agent (Worker)
└── reviewer.py         # Reviewer Agent (Quality Gate)
```

## Agents

### Manager Agent (`manager.py`)

The orchestrator that coordinates the hierarchical system.

**State Machine:**
```
INIT → DECOMPOSE → DISPATCH → MONITOR → SYNTHESIZE → COMPLETE
```

**Responsibilities:**
- Task decomposition and prioritization
- Work distribution to specialized agents
- Progress monitoring and convergence detection
- Conflict resolution and synthesis
- Quality gate enforcement

### Coder Agent (`coder.py`)

Worker agent for code generation and modification.

**State Machine:**
```
IDLE → ASSIGNED → IMPLEMENTING → REVIEW → DONE
                               ↓
                            REVISION (if review fails)
```

**Capabilities:**
- Feature implementation
- Bug fixing
- Code refactoring
- Documentation generation

### Reviewer Agent (`reviewer.py`)

Worker agent for quality assurance and code review.

**State Machine:**
```
IDLE → REVIEWING → APPROVED or NEEDS_CHANGES or REJECTED
```

**Capabilities:**
- Code review with checklist analysis
- Acceptance criteria validation
- Standards compliance checking
- Issue detection (bugs, security, anti-patterns)

## Communication Protocol

Agents communicate using typed messages:

```python
@dataclass
class AgentMessage:
    id: str
    sender: AgentRole
    receiver: AgentRole
    type: MessageType  # task_assignment, task_completed, review_request, etc.
    payload: Any
    timestamp: str
    correlation_id: Optional[str]
```

Message types:
- `TASK_ASSIGNMENT`: Manager → Worker
- `TASK_COMPLETED`: Worker → Manager
- `REVIEW_REQUEST`: Coder → Reviewer
- `REVIEW_RESULT`: Reviewer → Coder/Manager
- `CONFLICT_REPORT`: Worker → Manager
- `STATUS_UPDATE`: Any → Manager
- `ERROR_REPORT`: Any → Manager

## Usage Example

```python
from src.agents import ManagerAgent
from src.agents.base import TaskSpec

# Create and initialize manager
manager = ManagerAgent(
    mcp_config_path="~/.config/autodev/mcp_config.json",
    repo_root="."
)
await manager.initialize()

# Execute a task
task = TaskSpec(
    task_type="implement",
    specification="Add user authentication with OAuth2",
    target_files=["src/auth.py"],
    constraints={"preserve_api": True}
)
result = await manager.execute(task)

print(f"Status: {result.status}")
print(f"Files modified: {result.files_modified}")
print(f"Summary: {result.summary}")

# Shutdown
await manager.shutdown()
```

## MCP Integration

Agents require MCP (Model Context Protocol) servers for tool access:

| Server | Purpose | Priority |
|--------|---------|----------|
| `filesystem` | File operations | Critical |
| `git` | Version control | Critical |
| `lsp` | Code intelligence | High |
| `terminal` | Command execution | High |

MCP integration will be implemented in Phase 2.

## State Machine Pattern

All agents use the `StateMachine` class for state management:

```python
from src.agents.states import StateMachine, ManagerState

# Create state machine
sm = StateMachine(
    initial_state=ManagerState.INIT,
    valid_transitions=MANAGER_TRANSITIONS
)

# Transition
sm.transition(ManagerState.DECOMPOSE, reason="Task loaded")

# Check current state
print(sm.current_state)  # ManagerState.DECOMPOSE

# Get history
history = sm.get_history(limit=10)
```

## Phase 1 Status

- [x] Base agent class and interfaces
- [x] State machine definitions
- [x] Communication protocol
- [x] Manager Agent scaffold
- [x] Coder Agent scaffold
- [x] Reviewer Agent scaffold

## Next Steps (Phase 2)

1. Implement MCP client for tool access
2. Create custom MCP servers (terminal, testing)
3. Connect agents to actual LLM backends
4. Implement actual task decomposition logic
5. Add Hermes integration

## Architecture Reference

See [Hierarchical Architecture Specification](~/Documents/Obsidian/Hermes/Knowledge/AutoDev/Hierarchical_Architecture_Spec.md) for complete design documentation.
