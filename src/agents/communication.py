"""
Inter-Agent Communication Protocol

Implements the communication protocol between agents as specified in 
the Hierarchical Architecture Specification.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import json
import uuid

from .base import AgentRole


class MessageType(Enum):
    """
    Types of messages exchanged between agents.
    
    As specified in Section 6.1 of the architecture spec.
    """
    TASK_ASSIGNMENT = "task_assignment"      # Manager → Worker
    TASK_COMPLETED = "task_completed"         # Worker → Manager
    REVIEW_REQUEST = "review_request"         # Coder → Reviewer
    REVIEW_RESULT = "review_result"           # Reviewer → Coder/Manager
    CONFLICT_REPORT = "conflict_report"       # Worker → Manager
    STATUS_UPDATE = "status_update"           # Any → Manager
    ERROR_REPORT = "error_report"             # Any → Manager


@dataclass
class AgentMessage:
    """
    Message exchanged between agents.
    
    As specified in Section 6.1 of the architecture spec.
    
    Attributes:
        id: Unique message ID
        sender: Agent role sending the message
        receiver: Target agent role
        type: Message type
        payload: Message content
        timestamp: ISO 8601 timestamp
        correlation_id: Optional ID for request-response correlation
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender: AgentRole = AgentRole.MANAGER
    receiver: AgentRole = AgentRole.CODER
    type: MessageType = MessageType.TASK_ASSIGNMENT
    payload: Any = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    correlation_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary for serialization."""
        return {
            "id": self.id,
            "sender": self.sender.value,
            "receiver": self.receiver.value,
            "type": self.type.value,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id
        }
    
    def to_json(self) -> str:
        """Serialize message to JSON."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentMessage":
        """Create message from dictionary."""
        return cls(
            id=data["id"],
            sender=AgentRole(data["sender"]),
            receiver=AgentRole(data["receiver"]),
            type=MessageType(data["type"]),
            payload=data["payload"],
            timestamp=data["timestamp"],
            correlation_id=data.get("correlation_id")
        )


@dataclass
class TaskAssignment:
    """
    Task assignment message from Manager to Worker.
    
    As specified in Section 6.2 of the architecture spec.
    
    Attributes:
        task_id: Unique task identifier
        task_type: Type of task (implement, review, test, refactor)
        priority: Priority level (critical, high, medium, low)
        specification: Task specification text
        context: Context including relevant files and constraints
        dependencies: List of blocking task IDs
        timeout_seconds: Maximum execution time
        retry_policy: Retry configuration
    """
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_type: str = "implement"
    priority: str = "medium"
    specification: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    timeout_seconds: int = 300
    retry_policy: Dict[str, Any] = field(default_factory=lambda: {
        "max_retries": 2,
        "backoff_seconds": 30
    })
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "priority": self.priority,
            "specification": self.specification,
            "context": self.context,
            "dependencies": self.dependencies,
            "timeout_seconds": self.timeout_seconds,
            "retry_policy": self.retry_policy
        }


@dataclass
class Finding:
    """
    A finding from code review.
    
    Attributes:
        category: Category (correctness, quality, security, performance, style)
        severity: Severity level (blocking, major, minor, suggestion)
        file: File path
        line: Optional line number
        description: Description of the finding
        recommendation: Recommended fix
    """
    category: str
    severity: str
    file: str
    line: Optional[int] = None
    description: str = ""
    recommendation: str = ""


@dataclass
class ReviewResult:
    """
    Review result from Reviewer Agent.
    
    As specified in Section 6.3 of the architecture spec.
    
    Attributes:
        review_id: Unique review identifier
        task_id: Task being reviewed
        verdict: Review verdict (approved, needs_changes, rejected)
        findings: List of findings
        summary: Summary of the review
        blocking_issues: List of blocking issue descriptions
    """
    review_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""
    verdict: str = "approved"  # approved, needs_changes, rejected
    findings: List[Finding] = field(default_factory=list)
    summary: str = ""
    blocking_issues: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "review_id": self.review_id,
            "task_id": self.task_id,
            "verdict": self.verdict,
            "findings": [
                {
                    "category": f.category,
                    "severity": f.severity,
                    "file": f.file,
                    "line": f.line,
                    "description": f.description,
                    "recommendation": f.recommendation
                }
                for f in self.findings
            ],
            "summary": self.summary,
            "blocking_issues": self.blocking_issues
        }


@dataclass
class ConflictReport:
    """
    Report of conflicting changes from parallel workers.
    
    Attributes:
        conflict_id: Unique identifier
        files: Files with conflicts
        workers: Worker agents involved
        description: Description of the conflict
        suggested_resolution: Optional suggested resolution
    """
    conflict_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    files: List[str] = field(default_factory=list)
    workers: List[str] = field(default_factory=list)
    description: str = ""
    suggested_resolution: Optional[str] = None


@dataclass
class StatusUpdate:
    """
    Status update from a worker agent.
    
    Attributes:
        task_id: Task being worked on
        agent_id: Agent providing the update
        status: Current status
        progress: Progress percentage (0-100)
        message: Human-readable status message
        files_modified: Files modified so far
    """
    task_id: str = ""
    agent_id: str = ""
    status: str = "in_progress"
    progress: int = 0
    message: str = ""
    files_modified: List[str] = field(default_factory=list)


@dataclass
class ErrorReport:
    """
    Error report from an agent.
    
    Attributes:
        task_id: Task that encountered the error
        agent_id: Agent reporting the error
        error_type: Classification of the error
        error_message: Detailed error message
        recoverable: Whether the error is recoverable
        stack_trace: Optional stack trace
    """
    task_id: str = ""
    agent_id: str = ""
    error_type: str = "unknown"
    error_message: str = ""
    recoverable: bool = True
    stack_trace: Optional[str] = None


class MessageRouter:
    """
    Routes messages between agents.
    
    In Phase 1, this is a simple in-memory implementation.
    Future phases may use message queues or other infrastructure.
    """
    
    def __init__(self):
        self._queues: Dict[AgentRole, List[AgentMessage]] = {
            role: [] for role in AgentRole
        }
    
    def send(self, message: AgentMessage) -> None:
        """
        Send a message to a target agent's queue.
        
        Args:
            message: Message to send
        """
        self._queues[message.receiver].append(message)
    
    def receive(self, role: AgentRole) -> Optional[AgentMessage]:
        """
        Receive the next message for a role.
        
        Args:
            role: Role to receive for
            
        Returns:
            Next message or None if queue is empty
        """
        queue = self._queues.get(role, [])
        if queue:
            return queue.pop(0)
        return None
    
    def peek(self, role: AgentRole) -> Optional[AgentMessage]:
        """
        Peek at the next message without removing it.
        
        Args:
            role: Role to peek for
            
        Returns:
            Next message or None if queue is empty
        """
        queue = self._queues.get(role, [])
        if queue:
            return queue[0]
        return None
    
    def get_queue_length(self, role: AgentRole) -> int:
        """Get the number of pending messages for a role."""
        return len(self._queues.get(role, []))
