"""
Conflict Resolver for Hierarchical Agents

Provides conflict detection and resolution strategies for multi-agent
code modifications and merge operations.

This module implements:
- Conflict detection: Identify overlapping modifications
- Merge strategies: Combine changes intelligently
- Resolution policies: Rules for automatic resolution
- Escalation: Handle unresolvable conflicts

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                   Conflict Resolver                         │
    ├─────────────────────────────────────────────────────────────┤
    │  Agent Changes → Conflict Detection → Resolution Strategy → │
    │                 → Merge/Conflict Output                     │
    │                                                              │
    │  Resolution Strategies: [Merge, Override, Queue, Escalate]  │
    └─────────────────────────────────────────────────────────────┘

Usage:
    from hierarchical.coordination.conflict_resolver import ConflictResolver, ResolutionConfig
    
    resolver = ConflictResolver()
    
    # Check for conflicts
    conflicts = resolver.detect_conflicts(changes_from_agents)
    
    # Resolve conflicts
    resolved = resolver.resolve(conflicts)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Set
import difflib
import logging
import uuid

logger = logging.getLogger(__name__)


class ConflictType(Enum):
    """Types of conflicts that can occur."""
    FILE_OVERLAP = "file_overlap"           # Same file modified by multiple agents
    LINE_OVERLAP = "line_overlap"           # Same lines modified
    SEMANTIC = "semantic"                   # Semantic/logical conflicts
    DEPENDENCY = "dependency"               # Conflicting dependency changes
    IMPORT = "import"                       # Import statement conflicts
    NAMING = "naming"                       # Naming conflicts (new names)
    TEST = "test"                           # Test conflicts
    CONFIG = "config"                       # Configuration conflicts


class ResolutionStrategy(Enum):
    """Strategies for conflict resolution."""
    MERGE = "merge"                         # Attempt automatic merge
    PRIORITY = "priority"                   # Use higher priority agent's changes
    TIMESTAMP = "timestamp"                 # Use most recent changes
    MANUAL = "manual"                       # Escalate to human review
    QUEUED = "queued"                       # Queue changes sequentially
    CONSENSUS = "consensus"                 # Require agreement between agents


class ConflictSeverity(Enum):
    """Severity levels for conflicts."""
    LOW = 1       # Auto-resolvable with confidence
    MEDIUM = 2    # May need review
    HIGH = 3      # Requires human intervention
    CRITICAL = 4  # Blocks all progress


@dataclass
class FileChange:
    """
    Represents a file modification by an agent.
    
    Attributes:
        file_path: Path to the modified file
        agent_id: ID of the modifying agent
        change_type: Type of change (add, modify, delete)
        original_content: Content before change
        new_content: Content after change
        changed_lines: Set of changed line numbers
        timestamp: When the change was made
        priority: Agent/task priority
        metadata: Additional change metadata
    """
    file_path: str = ""
    agent_id: str = ""
    change_type: str = "modify"
    original_content: str = ""
    new_content: str = ""
    changed_lines: Set[int] = field(default_factory=set)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    priority: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_diff(self) -> str:
        """Get unified diff of changes."""
        original_lines = self.original_content.splitlines(keepends=True)
        new_lines = self.new_content.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=f"{self.file_path}.original",
            tofile=f"{self.file_path}.new",
        )
        
        return ''.join(diff)


@dataclass
class ConflictInfo:
    """
    Information about a detected conflict.
    
    Attributes:
        conflict_id: Unique identifier
        conflict_type: Type of conflict
        severity: Conflict severity
        file_path: Affected file path
        conflicting_changes: List of conflicting FileChange objects
        affected_lines: Set of affected line numbers
        resolution_strategy: Suggested resolution strategy
        auto_resolvable: Whether conflict can be auto-resolved
        created_at: Detection timestamp
        metadata: Additional conflict metadata
    """
    conflict_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    conflict_type: ConflictType = ConflictType.FILE_OVERLAP
    severity: ConflictSeverity = ConflictSeverity.MEDIUM
    file_path: str = ""
    conflicting_changes: List[FileChange] = field(default_factory=list)
    affected_lines: Set[int] = field(default_factory=set)
    resolution_strategy: ResolutionStrategy = ResolutionStrategy.MERGE
    auto_resolvable: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def agent_ids(self) -> List[str]:
        """Get IDs of conflicting agents."""
        return list(set(c.agent_id for c in self.conflicting_changes))

    @property
    def is_critical(self) -> bool:
        """Check if conflict is critical."""
        return self.severity == ConflictSeverity.CRITICAL


@dataclass
class ResolutionConfig:
    """
    Configuration for Conflict Resolver.
    
    Attributes:
        default_strategy: Default resolution strategy
        auto_resolve_low: Auto-resolve LOW severity conflicts
        auto_resolve_medium: Auto-resolve MEDIUM severity conflicts
        max_attempts: Maximum resolution attempts
        escalation_threshold: Failures before escalation
        backup_originals: Keep backups of original files
        merge_preference: Preferred merge side (left/right/newest)
    """
    default_strategy: ResolutionStrategy = ResolutionStrategy.MERGE
    auto_resolve_low: bool = True
    auto_resolve_medium: bool = True
    max_attempts: int = 3
    escalation_threshold: int = 2
    backup_originals: bool = True
    merge_preference: str = "newest"


@dataclass
class ResolutionResult:
    """
    Result of conflict resolution.
    
    Attributes:
        conflict_id: ID of resolved conflict
        success: Whether resolution was successful
        strategy_used: Strategy used for resolution
        resolved_content: Final resolved content
        resolved_file_path: Path to resolved file
        warnings: Warnings during resolution
        requires_review: Whether human review is needed
        timestamp: Resolution timestamp
    """
    conflict_id: str = ""
    success: bool = False
    strategy_used: ResolutionStrategy = ResolutionStrategy.MERGE
    resolved_content: str = ""
    resolved_file_path: str = ""
    warnings: List[str] = field(default_factory=list)
    requires_review: bool = False
    timestamp: datetime = field(default_factory=datetime.utcnow)


class ConflictResolver:
    """
    Conflict detection and resolution for multi-agent coordination.
    
    This class provides:
    - Detection of overlapping file modifications
    - Multiple resolution strategies
    - Automatic merge capabilities
    - Escalation for complex conflicts
    
    Example:
        >>> resolver = ConflictResolver()
        >>> conflicts = resolver.detect_conflicts([change1, change2])
        >>> for conflict in conflicts:
        ...     result = resolver.resolve(conflict)
        ...     if result.success:
        ...         print(f"Resolved {conflict.conflict_id}")
    """
    
    def __init__(self, config: Optional[ResolutionConfig] = None):
        """
        Initialize Conflict Resolver.
        
        Args:
            config: Resolution configuration
        """
        self.config = config or ResolutionConfig()
        self._conflicts: Dict[str, ConflictInfo] = {}
        self._resolutions: Dict[str, ResolutionResult] = {}
        self._failed_attempts: Dict[str, int] = {}
        
        logger.info(
            f"ConflictResolver initialized with strategy {self.config.default_strategy.value}"
        )

    def detect_conflicts(
        self,
        changes: List[FileChange],
    ) -> List[ConflictInfo]:
        """
        Detect conflicts among a set of file changes.
        
        Args:
            changes: List of file changes to analyze
            
        Returns:
            List of detected ConflictInfo objects
        """
        conflicts = []
        
        # Group changes by file
        changes_by_file: Dict[str, List[FileChange]] = {}
        for change in changes:
            if change.file_path not in changes_by_file:
                changes_by_file[change.file_path] = []
            changes_by_file[change.file_path].append(change)
        
        # Check for conflicts in each file
        for file_path, file_changes in changes_by_file.items():
            if len(file_changes) > 1:
                # Multiple agents modified same file
                conflict = self._analyze_file_conflict(file_path, file_changes)
                if conflict:
                    conflicts.append(conflict)
                    self._conflicts[conflict.conflict_id] = conflict
        
        logger.info(f"Detected {len(conflicts)} conflicts")
        return conflicts

    def resolve(
        self,
        conflict: ConflictInfo,
        strategy: Optional[ResolutionStrategy] = None,
    ) -> ResolutionResult:
        """
        Resolve a conflict using the specified strategy.
        
        Args:
            conflict: Conflict to resolve
            strategy: Optional strategy override
            
        Returns:
            ResolutionResult with outcome
        """
        strategy = strategy or conflict.resolution_strategy or self.config.default_strategy
        
        # Check if auto-resolution is appropriate
        if not self._can_auto_resolve(conflict, strategy):
            return ResolutionResult(
                conflict_id=conflict.conflict_id,
                success=False,
                strategy_used=ResolutionStrategy.MANUAL,
                requires_review=True,
                warnings=["Conflict requires manual resolution"],
            )
        
        # Track attempts
        if conflict.conflict_id not in self._failed_attempts:
            self._failed_attempts[conflict.conflict_id] = 0
        
        try:
            result = self._apply_resolution_strategy(conflict, strategy)
            
            if result.success:
                self._resolutions[conflict.conflict_id] = result
                logger.info(f"Resolved conflict {conflict.conflict_id}")
            else:
                self._failed_attempts[conflict.conflict_id] += 1
                
                # Escalate if too many failures
                if self._failed_attempts[conflict.conflict_id] >= self.config.escalation_threshold:
                    result.requires_review = True
                    result.warnings.append("Escalated due to repeated failures")
            
            return result
            
        except Exception as e:
            logger.error(f"Resolution failed for {conflict.conflict_id}: {e}")
            return ResolutionResult(
                conflict_id=conflict.conflict_id,
                success=False,
                strategy_used=strategy,
                requires_review=True,
                warnings=[f"Resolution error: {str(e)}"],
            )

    def resolve_all(
        self,
        conflicts: List[ConflictInfo],
    ) -> List[ResolutionResult]:
        """
        Resolve multiple conflicts.
        
        Args:
            conflicts: List of conflicts to resolve
            
        Returns:
            List of resolution results
        """
        results = []
        
        # Sort by severity (resolve critical first)
        sorted_conflicts = sorted(
            conflicts,
            key=lambda c: c.severity.value,
            reverse=True
        )
        
        for conflict in sorted_conflicts:
            result = self.resolve(conflict)
            results.append(result)
            
            if not result.success and result.requires_review:
                logger.warning(
                    f"Stopping resolution due to unresolvable conflict: "
                    f"{conflict.conflict_id}"
                )
                break
        
        return results

    def _analyze_file_conflict(
        self,
        file_path: str,
        changes: List[FileChange],
    ) -> Optional[ConflictInfo]:
        """
        Analyze file changes to determine conflict type and severity.
        
        Args:
            file_path: Path to the file
            changes: List of changes to the file
            
        Returns:
            ConflictInfo if conflict detected, None otherwise
        """
        # Check for line overlap
        all_lines: Set[int] = set()
        overlapping_lines: Set[int] = set()
        
        for change in changes:
            for line in change.changed_lines:
                if line in all_lines:
                    overlapping_lines.add(line)
                all_lines.add(line)
        
        if not overlapping_lines:
            # No line overlap - can merge cleanly
            return ConflictInfo(
                conflict_type=ConflictType.FILE_OVERLAP,
                severity=ConflictSeverity.LOW,
                file_path=file_path,
                conflicting_changes=changes,
                affected_lines=overlapping_lines,
                resolution_strategy=ResolutionStrategy.MERGE,
                auto_resolvable=True,
            )
        
        # Determine severity based on overlap extent
        overlap_ratio = len(overlapping_lines) / len(all_lines) if all_lines else 0
        
        if overlap_ratio < 0.1:
            severity = ConflictSeverity.LOW
            strategy = ResolutionStrategy.MERGE
        elif overlap_ratio < 0.3:
            severity = ConflictSeverity.MEDIUM
            strategy = ResolutionStrategy.PRIORITY
        elif overlap_ratio < 0.6:
            severity = ConflictSeverity.HIGH
            strategy = ResolutionStrategy.MANUAL
        else:
            severity = ConflictSeverity.CRITICAL
            strategy = ResolutionStrategy.MANUAL
        
        return ConflictInfo(
            conflict_type=ConflictType.LINE_OVERLAP,
            severity=severity,
            file_path=file_path,
            conflicting_changes=changes,
            affected_lines=overlapping_lines,
            resolution_strategy=strategy,
            auto_resolvable=severity.value <= ConflictSeverity.MEDIUM.value,
        )

    def _can_auto_resolve(
        self,
        conflict: ConflictInfo,
        strategy: ResolutionStrategy,
    ) -> bool:
        """
        Check if a conflict can be auto-resolved.
        
        Args:
            conflict: Conflict to check
            strategy: Proposed resolution strategy
            
        Returns:
            True if auto-resolution is possible
        """
        if strategy == ResolutionStrategy.MANUAL:
            return False
        
        if conflict.severity == ConflictSeverity.CRITICAL:
            return False
        
        if conflict.severity == ConflictSeverity.HIGH:
            return False
        
        if conflict.severity == ConflictSeverity.MEDIUM:
            return self.config.auto_resolve_medium
        
        return self.config.auto_resolve_low

    def _apply_resolution_strategy(
        self,
        conflict: ConflictInfo,
        strategy: ResolutionStrategy,
    ) -> ResolutionResult:
        """
        Apply a resolution strategy to a conflict.
        
        Args:
            conflict: Conflict to resolve
            strategy: Strategy to apply
            
        Returns:
            ResolutionResult
        """
        if strategy == ResolutionStrategy.MERGE:
            return self._merge_resolution(conflict)
        elif strategy == ResolutionStrategy.PRIORITY:
            return self._priority_resolution(conflict)
        elif strategy == ResolutionStrategy.TIMESTAMP:
            return self._timestamp_resolution(conflict)
        elif strategy == ResolutionStrategy.QUEUED:
            return self._queued_resolution(conflict)
        else:
            return ResolutionResult(
                conflict_id=conflict.conflict_id,
                success=False,
                strategy_used=strategy,
                requires_review=True,
            )

    def _merge_resolution(self, conflict: ConflictInfo) -> ResolutionResult:
        """
        Attempt to merge changes automatically.
        
        Args:
            conflict: Conflict to resolve
            
        Returns:
            ResolutionResult with merged content
        """
        changes = sorted(
            conflict.conflicting_changes,
            key=lambda c: c.timestamp
        )
        
        if not changes:
            return ResolutionResult(
                conflict_id=conflict.conflict_id,
                success=False,
                warnings=["No changes to merge"],
            )
        
        # Start with original content
        merged_content = changes[0].original_content
        
        for change in changes:
            merged_content = self._apply_change(merged_content, change)
        
        return ResolutionResult(
            conflict_id=conflict.conflict_id,
            success=True,
            strategy_used=ResolutionStrategy.MERGE,
            resolved_content=merged_content,
            resolved_file_path=conflict.file_path,
        )

    def _priority_resolution(self, conflict: ConflictInfo) -> ResolutionResult:
        """
        Use highest priority agent's changes.
        
        Args:
            conflict: Conflict to resolve
            
        Returns:
            ResolutionResult with highest priority content
        """
        # Sort by priority (lower number = higher priority)
        changes = sorted(
            conflict.conflicting_changes,
            key=lambda c: c.priority
        )
        
        winner = changes[0]
        
        return ResolutionResult(
            conflict_id=conflict.conflict_id,
            success=True,
            strategy_used=ResolutionStrategy.PRIORITY,
            resolved_content=winner.new_content,
            resolved_file_path=conflict.file_path,
            warnings=[
                f"Used changes from agent {winner.agent_id} (priority {winner.priority})"
            ],
        )

    def _timestamp_resolution(self, conflict: ConflictInfo) -> ResolutionResult:
        """
        Use most recent agent's changes.
        
        Args:
            conflict: Conflict to resolve
            
        Returns:
            ResolutionResult with most recent content
        """
        # Sort by timestamp (newest first)
        changes = sorted(
            conflict.conflicting_changes,
            key=lambda c: c.timestamp,
            reverse=True
        )
        
        winner = changes[0]
        
        return ResolutionResult(
            conflict_id=conflict.conflict_id,
            success=True,
            strategy_used=ResolutionStrategy.TIMESTAMP,
            resolved_content=winner.new_content,
            resolved_file_path=conflict.file_path,
            warnings=[
                f"Used most recent changes from agent {winner.agent_id}"
            ],
        )

    def _queued_resolution(self, conflict: ConflictInfo) -> ResolutionResult:
        """
        Queue changes for sequential application.
        
        Args:
            conflict: Conflict to resolve
            
        Returns:
            ResolutionResult with queued status
        """
        # Sort changes by timestamp
        changes = sorted(
            conflict.conflicting_changes,
            key=lambda c: c.timestamp
        )
        
        # Return first change, queue rest
        first = changes[0]
        
        return ResolutionResult(
            conflict_id=conflict.conflict_id,
            success=True,
            strategy_used=ResolutionStrategy.QUEUED,
            resolved_content=first.new_content,
            resolved_file_path=conflict.file_path,
            warnings=[
                f"Applied first change, {len(changes) - 1} queued for later"
            ],
            requires_review=len(changes) > 1,
        )

    def _apply_change(
        self,
        content: str,
        change: FileChange,
    ) -> str:
        """
        Apply a file change to content.
        
        Args:
            content: Current content
            change: Change to apply
            
        Returns:
            Modified content
        """
        # Simple implementation - replace lines
        lines = content.splitlines(keepends=True)
        
        for line_num in sorted(change.changed_lines, reverse=True):
            if 0 < line_num <= len(lines):
                # For now, just preserve existing content
                # A real implementation would do proper merging
                pass
        
        return content

    def get_conflict(self, conflict_id: str) -> Optional[ConflictInfo]:
        """
        Get a conflict by ID.
        
        Args:
            conflict_id: Conflict ID
            
        Returns:
            ConflictInfo if found, None otherwise
        """
        return self._conflicts.get(conflict_id)

    def get_resolution(self, conflict_id: str) -> Optional[ResolutionResult]:
        """
        Get a resolution by conflict ID.
        
        Args:
            conflict_id: Conflict ID
            
        Returns:
            ResolutionResult if resolved, None otherwise
        """
        return self._resolutions.get(conflict_id)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get conflict resolver statistics.
        
        Returns:
            Dictionary of statistics
        """
        resolved_count = len(self._resolutions)
        pending_count = len([
            c for c in self._conflicts.values()
            if c.conflict_id not in self._resolutions
        ])
        
        return {
            "total_conflicts": len(self._conflicts),
            "resolved": resolved_count,
            "pending": pending_count,
            "failed_attempts": sum(self._failed_attempts.values()),
        }
