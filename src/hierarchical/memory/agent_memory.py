"""
Agent Memory System

Provides persistent memory storage for hierarchical agents, enabling
cross-task learning and context preservation.

This module implements:
- Experience traces: Record of agent actions and outcomes
- Knowledge storage: Persistent facts and patterns learned
- Memory retrieval: Relevant memory lookup for current tasks

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                     Agent Memory                            │
    ├─────────────────────────────────────────────────────────────┤
    │  Task Execution → Experience Trace → Knowledge Extraction → │
    │                  → Persistent Storage                       │
    │                                                              │
    │  New Task → Context Retrieval → Relevant Experiences → Agent│
    └─────────────────────────────────────────────────────────────┘

Usage:
    from hierarchical.memory.agent_memory import AgentMemory, MemoryConfig
    
    config = MemoryConfig(storage_path="./memory")
    memory = AgentMemory(agent_id="coder_1", config=config)
    
    # Store experience
    memory.store_experience(task_id, trace)
    
    # Retrieve relevant experiences
    experiences = memory.retrieve_relevant(current_task)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import json
import logging
import os
import uuid

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """Types of memory entries."""
    EXPERIENCE = "experience"
    KNOWLEDGE = "knowledge"
    PATTERN = "pattern"
    ERROR = "error"
    SUCCESS = "success"


class MemoryPriority(Enum):
    """Priority levels for memory retention."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class MemoryConfig:
    """
    Configuration for Agent Memory.
    
    Attributes:
        storage_path: Directory for persistent storage
        max_entries: Maximum number of entries to retain
        max_age_days: Maximum age of entries before cleanup
        enable_compression: Compress stored entries
        index_fields: Fields to index for retrieval
        relevance_threshold: Minimum relevance score for retrieval
    """
    storage_path: str = "./agent_memory"
    max_entries: int = 10000
    max_age_days: int = 30
    enable_compression: bool = True
    index_fields: List[str] = field(default_factory=lambda: [
        "task_type", "files_modified", "tags"
    ])
    relevance_threshold: float = 0.5


@dataclass
class MemoryEntry:
    """
    A single memory entry in agent memory.
    
    Attributes:
        entry_id: Unique identifier
        memory_type: Type of memory
        agent_id: Agent that created this memory
        task_id: Associated task ID
        timestamp: Creation timestamp
        content: Main memory content
        metadata: Additional metadata
        tags: Tags for categorization
        priority: Retention priority
        access_count: Number of times accessed
        last_accessed: Last access timestamp
    """
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    memory_type: MemoryType = MemoryType.EXPERIENCE
    agent_id: str = ""
    task_id: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    content: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    priority: MemoryPriority = MemoryPriority.MEDIUM
    access_count: int = 0
    last_accessed: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "entry_id": self.entry_id,
            "memory_type": self.memory_type.value,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "timestamp": self.timestamp.isoformat(),
            "content": self.content,
            "metadata": self.metadata,
            "tags": self.tags,
            "priority": self.priority.value,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        """Create from dictionary."""
        return cls(
            entry_id=data["entry_id"],
            memory_type=MemoryType(data["memory_type"]),
            agent_id=data["agent_id"],
            task_id=data["task_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            content=data["content"],
            metadata=data["metadata"],
            tags=data["tags"],
            priority=MemoryPriority(data["priority"]),
            access_count=data["access_count"],
            last_accessed=(
                datetime.fromisoformat(data["last_accessed"])
                if data.get("last_accessed") else None
            ),
        )


@dataclass
class ExperienceTrace:
    """
    Trace of an agent's experience during task execution.
    
    Attributes:
        trace_id: Unique identifier
        task_id: Associated task ID
        agent_id: Agent that generated this trace
        task_type: Type of task performed
        steps: List of steps taken
        files_modified: Files that were modified
        outcome: Final outcome (success/failure)
        error: Error message if failed
        lessons_learned: Key lessons from this experience
        duration_seconds: Total execution time
        timestamp: Trace creation timestamp
    """
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""
    agent_id: str = ""
    task_type: str = ""
    steps: List[Dict[str, Any]] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    outcome: str = "unknown"
    error: Optional[str] = None
    lessons_learned: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_memory_entry(self) -> MemoryEntry:
        """Convert to a MemoryEntry for storage."""
        return MemoryEntry(
            memory_type=(
                MemoryType.SUCCESS if self.outcome == "success"
                else MemoryType.ERROR
            ),
            agent_id=self.agent_id,
            task_id=self.task_id,
            content={
                "steps": self.steps,
                "files_modified": self.files_modified,
                "outcome": self.outcome,
                "error": self.error,
                "lessons_learned": self.lessons_learned,
                "duration_seconds": self.duration_seconds,
            },
            metadata={
                "task_type": self.task_type,
            },
            tags=[self.task_type] + self.files_modified[:5],
            priority=(
                MemoryPriority.HIGH if self.outcome == "success"
                else MemoryPriority.CRITICAL
            ),
        )


class AgentMemory:
    """
    Persistent memory system for hierarchical agents.
    
    This class provides:
    - Storage and retrieval of agent experiences
    - Knowledge extraction from successful patterns
    - Relevant memory lookup for current tasks
    
    Example:
        >>> memory = AgentMemory(agent_id="coder_1")
        >>> memory.store_experience(trace)
        >>> relevant = memory.retrieve_relevant(task_spec)
    """
    
    def __init__(
        self,
        agent_id: str,
        config: Optional[MemoryConfig] = None,
    ):
        """
        Initialize Agent Memory.
        
        Args:
            agent_id: ID of the agent using this memory
            config: Memory configuration
        """
        self.agent_id = agent_id
        self.config = config or MemoryConfig()
        self._entries: Dict[str, MemoryEntry] = {}
        self._indices: Dict[str, Dict[str, List[str]]] = {}
        
        # Initialize storage
        self._initialize_storage()
        
        logger.info(f"AgentMemory initialized for agent {agent_id}")

    def _initialize_storage(self) -> None:
        """Initialize storage directory and load existing entries."""
        os.makedirs(self.config.storage_path, exist_ok=True)
        
        # Load existing entries
        memory_file = os.path.join(
            self.config.storage_path,
            f"{self.agent_id}_memory.json"
        )
        
        if os.path.exists(memory_file):
            try:
                with open(memory_file, "r") as f:
                    data = json.load(f)
                    for entry_data in data.get("entries", []):
                        entry = MemoryEntry.from_dict(entry_data)
                        self._entries[entry.entry_id] = entry
                        self._index_entry(entry)
                logger.info(f"Loaded {len(self._entries)} memory entries")
            except Exception as e:
                logger.error(f"Failed to load memory: {e}")

    def store_experience(self, trace: ExperienceTrace) -> MemoryEntry:
        """
        Store an experience trace in memory.
        
        Args:
            trace: Experience trace to store
            
        Returns:
            Created MemoryEntry
        """
        entry = trace.to_memory_entry()
        entry.agent_id = self.agent_id
        
        self._entries[entry.entry_id] = entry
        self._index_entry(entry)
        
        # Persist to storage
        self._persist()
        
        logger.debug(f"Stored experience {entry.entry_id}")
        return entry

    def store_knowledge(
        self,
        knowledge: Dict[str, Any],
        tags: List[str],
        priority: MemoryPriority = MemoryPriority.HIGH,
    ) -> MemoryEntry:
        """
        Store extracted knowledge in memory.
        
        Args:
            knowledge: Knowledge content
            tags: Tags for categorization
            priority: Retention priority
            
        Returns:
            Created MemoryEntry
        """
        entry = MemoryEntry(
            memory_type=MemoryType.KNOWLEDGE,
            agent_id=self.agent_id,
            content=knowledge,
            tags=tags,
            priority=priority,
        )
        
        self._entries[entry.entry_id] = entry
        self._index_entry(entry)
        self._persist()
        
        logger.debug(f"Stored knowledge {entry.entry_id}")
        return entry

    def retrieve_relevant(
        self,
        task_spec: Dict[str, Any],
        limit: int = 10,
    ) -> List[MemoryEntry]:
        """
        Retrieve memories relevant to a task specification.
        
        Args:
            task_spec: Task specification to match against
            limit: Maximum number of entries to return
            
        Returns:
            List of relevant MemoryEntry objects
        """
        # Calculate relevance scores
        scored_entries = []
        
        for entry in self._entries.values():
            score = self._calculate_relevance(entry, task_spec)
            if score >= self.config.relevance_threshold:
                scored_entries.append((score, entry))
        
        # Sort by relevance and return top entries
        scored_entries.sort(key=lambda x: x[0], reverse=True)
        
        # Update access counts
        results = []
        for score, entry in scored_entries[:limit]:
            entry.access_count += 1
            entry.last_accessed = datetime.utcnow()
            results.append(entry)
        
        if results:
            self._persist()
        
        return results

    def retrieve_by_type(
        self,
        memory_type: MemoryType,
        limit: int = 50,
    ) -> List[MemoryEntry]:
        """
        Retrieve entries by memory type.
        
        Args:
            memory_type: Type of memories to retrieve
            limit: Maximum number of entries
            
        Returns:
            List of matching MemoryEntry objects
        """
        entries = [
            e for e in self._entries.values()
            if e.memory_type == memory_type
        ]
        entries.sort(key=lambda x: x.timestamp, reverse=True)
        return entries[:limit]

    def retrieve_errors(self, limit: int = 20) -> List[MemoryEntry]:
        """
        Retrieve error memories for learning.
        
        Args:
            limit: Maximum number of entries
            
        Returns:
            List of error MemoryEntry objects
        """
        return self.retrieve_by_type(MemoryType.ERROR, limit)

    def retrieve_successes(self, limit: int = 20) -> List[MemoryEntry]:
        """
        Retrieve success memories for pattern learning.
        
        Args:
            limit: Maximum number of entries
            
        Returns:
            List of success MemoryEntry objects
        """
        return self.retrieve_by_type(MemoryType.SUCCESS, limit)

    def _index_entry(self, entry: MemoryEntry) -> None:
        """Index an entry for fast retrieval."""
        for field in self.config.index_fields:
            if field not in self._indices:
                self._indices[field] = {}
            
            value = getattr(entry, field, None) or entry.metadata.get(field)
            if value:
                if isinstance(value, list):
                    for v in value:
                        if v not in self._indices[field]:
                            self._indices[field][v] = []
                        self._indices[field][v].append(entry.entry_id)
                else:
                    if value not in self._indices[field]:
                        self._indices[field][value] = []
                    self._indices[field][value].append(entry.entry_id)

    def _calculate_relevance(
        self,
        entry: MemoryEntry,
        task_spec: Dict[str, Any],
    ) -> float:
        """
        Calculate relevance score between entry and task.
        
        Args:
            entry: Memory entry to score
            task_spec: Task specification
            
        Returns:
            Relevance score (0.0 to 1.0)
        """
        score = 0.0
        
        # Task type match
        entry_type = entry.metadata.get("task_type", "")
        task_type = task_spec.get("task_type", "")
        if entry_type and entry_type == task_type:
            score += 0.3
        
        # File overlap
        entry_files = set(entry.content.get("files_modified", []))
        task_files = set(task_spec.get("target_files", []))
        if entry_files and task_files:
            overlap = len(entry_files & task_files) / max(len(task_files), 1)
            score += 0.3 * overlap
        
        # Tag match
        task_tags = [task_type] + list(task_files)
        tag_matches = len(set(entry.tags) & set(task_tags))
        score += 0.2 * min(tag_matches / 3, 1.0)
        
        # Success bonus
        if entry.memory_type == MemoryType.SUCCESS:
            score += 0.1
        
        # Recency bonus
        age_days = (datetime.utcnow() - entry.timestamp).days
        if age_days < 7:
            score += 0.1
        elif age_days < 30:
            score += 0.05
        
        return min(score, 1.0)

    def _persist(self) -> None:
        """Persist memory to storage."""
        memory_file = os.path.join(
            self.config.storage_path,
            f"{self.agent_id}_memory.json"
        )
        
        try:
            data = {
                "agent_id": self.agent_id,
                "entries": [e.to_dict() for e in self._entries.values()],
            }
            with open(memory_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to persist memory: {e}")

    def cleanup(self) -> int:
        """
        Clean up old or low-priority entries.
        
        Returns:
            Number of entries removed
        """
        to_remove = []
        now = datetime.utcnow()
        
        for entry_id, entry in self._entries.items():
            age_days = (now - entry.timestamp).days
            if age_days > self.config.max_age_days and entry.priority.value < MemoryPriority.HIGH.value:
                to_remove.append(entry_id)
        
        for entry_id in to_remove:
            del self._entries[entry_id]
        
        if to_remove:
            self._persist()
            logger.info(f"Cleaned up {len(to_remove)} old memory entries")
        
        return len(to_remove)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get memory statistics.
        
        Returns:
            Dictionary of memory statistics
        """
        type_counts = {}
        for entry in self._entries.values():
            type_name = entry.memory_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
        
        return {
            "total_entries": len(self._entries),
            "by_type": type_counts,
            "storage_path": self.config.storage_path,
        }
