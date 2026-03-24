"""
State Machine Definitions

Implements state machines for AutoDev agents following the 
Hierarchical Architecture Specification.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class ManagerState(Enum):
    """
    Manager Agent state machine states.
    
    State transitions:
    INIT → DECOMPOSE → DISPATCH → MONITOR → SYNTHESIZE → COMPLETE
         ↑                                            ↓
         └────────────── (on retry) ←─────────────────┘
    """
    INIT = "init"                    # Load PRD, tracker, context
    DECOMPOSE = "decompose"          # Analyze requirements, create subtasks
    DISPATCH = "dispatch"            # Assign to workers, delegate
    MONITOR = "monitor"              # Track execution, handle failures
    SYNTHESIZE = "synthesize"        # Combine outputs, resolve conflicts
    COMPLETE = "complete"            # Final state


class CoderState(Enum):
    """
    Coder Agent state machine states.
    
    State transitions:
    IDLE → ASSIGNED → IMPLEMENTING → REVIEW → DONE
                                     ↓
                                  REVISION (if review fails)
    """
    IDLE = "idle"
    ASSIGNED = "assigned"
    IMPLEMENTING = "implementing"
    REVIEW = "review"
    REVISION = "revision"
    DONE = "done"


class ReviewerState(Enum):
    """
    Reviewer Agent state machine states.
    
    State transitions:
    IDLE → REVIEWING → APPROVED or NEEDS_CHANGES or REJECTED
    """
    IDLE = "idle"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    NEEDS_CHANGES = "needs_changes"
    REJECTED = "rejected"


@dataclass
class StateTransition:
    """
    Represents a state transition in the state machine.
    
    Attributes:
        from_state: Source state
        to_state: Target state
        timestamp: When the transition occurred
        reason: Optional reason for the transition
        metadata: Additional metadata about the transition
    """
    from_state: Enum
    to_state: Enum
    timestamp: datetime
    reason: Optional[str] = None
    metadata: Optional[Dict] = None


class StateMachine:
    """
    Generic state machine implementation.
    
    Manages state transitions with validation, logging, and callbacks.
    
    Attributes:
        current_state: Current state of the machine
        states: Valid states for this machine
        transitions: Allowed state transitions
        history: History of state transitions
    """
    
    def __init__(
        self,
        initial_state: Enum,
        valid_transitions: Dict[Enum, List[Enum]] = None
    ):
        self.current_state = initial_state
        self.valid_transitions = valid_transitions or {}
        self.history: List[StateTransition] = []
        self._callbacks: Dict[Enum, List[Callable]] = {}
    
    def can_transition_to(self, target_state: Enum) -> bool:
        """
        Check if transition to target state is allowed.
        
        Args:
            target_state: Target state to check
            
        Returns:
            True if transition is allowed
        """
        if not self.valid_transitions:
            return True  # Allow all transitions if not restricted
        
        allowed_states = self.valid_transitions.get(self.current_state, [])
        return target_state in allowed_states
    
    def transition(
        self,
        target_state: Enum,
        reason: str = None,
        metadata: Dict = None
    ) -> bool:
        """
        Transition to a new state.
        
        Args:
            target_state: Target state to transition to
            reason: Optional reason for transition
            metadata: Optional metadata
            
        Returns:
            True if transition succeeded
            
        Raises:
            ValueError: If transition is not allowed
        """
        if not self.can_transition_to(target_state):
            raise ValueError(
                f"Invalid transition from {self.current_state} to {target_state}"
            )
        
        old_state = self.current_state
        self.current_state = target_state
        
        transition_record = StateTransition(
            from_state=old_state,
            to_state=target_state,
            timestamp=datetime.now(timezone.utc),
            reason=reason,
            metadata=metadata
        )
        self.history.append(transition_record)
        
        logger.info(
            f"State transition: {old_state.value} → {target_state.value}"
            f"{f' ({reason})' if reason else ''}"
        )
        
        # Execute callbacks
        self._execute_callbacks(target_state, transition_record)
        
        return True
    
    def register_callback(
        self,
        state: Enum,
        callback: Callable[[StateTransition], None]
    ) -> None:
        """
        Register a callback to execute on entering a state.
        
        Args:
            state: State to trigger on
            callback: Callback function
        """
        if state not in self._callbacks:
            self._callbacks[state] = []
        self._callbacks[state].append(callback)
    
    def _execute_callbacks(
        self,
        state: Enum,
        transition: StateTransition
    ) -> None:
        """Execute registered callbacks for a state."""
        callbacks = self._callbacks.get(state, [])
        for callback in callbacks:
            try:
                callback(transition)
            except Exception as e:
                logger.error(f"Callback error on state {state}: {e}")
    
    def get_history(self, limit: int = 10) -> List[StateTransition]:
        """
        Get recent state transition history.
        
        Args:
            limit: Maximum number of transitions to return
            
        Returns:
            List of recent transitions
        """
        return self.history[-limit:]
    
    def is_terminal_state(self) -> bool:
        """
        Check if current state is terminal (no outgoing transitions).
        
        Returns:
            True if in a terminal state
        """
        if not self.valid_transitions:
            return False
        return len(self.valid_transitions.get(self.current_state, [])) == 0


# Manager state machine transition map
MANAGER_TRANSITIONS: Dict[ManagerState, List[ManagerState]] = {
    ManagerState.INIT: [ManagerState.DECOMPOSE],
    ManagerState.DECOMPOSE: [ManagerState.DISPATCH],
    ManagerState.DISPATCH: [ManagerState.MONITOR],
    ManagerState.MONITOR: [ManagerState.MONITOR, ManagerState.SYNTHESIZE, ManagerState.DISPATCH],
    ManagerState.SYNTHESIZE: [ManagerState.COMPLETE, ManagerState.MONITOR],
    ManagerState.COMPLETE: [],  # Terminal state
}


# Coder state machine transition map
CODER_TRANSITIONS: Dict[CoderState, List[CoderState]] = {
    CoderState.IDLE: [CoderState.ASSIGNED],
    CoderState.ASSIGNED: [CoderState.IMPLEMENTING],
    CoderState.IMPLEMENTING: [CoderState.REVIEW, CoderState.DONE],
    CoderState.REVIEW: [CoderState.DONE, CoderState.REVISION],
    CoderState.REVISION: [CoderState.IMPLEMENTING],
    CoderState.DONE: [CoderState.IDLE],  # Can accept new tasks
}


# Reviewer state machine transition map
REVIEWER_TRANSITIONS: Dict[ReviewerState, List[ReviewerState]] = {
    ReviewerState.IDLE: [ReviewerState.REVIEWING],
    ReviewerState.REVIEWING: [
        ReviewerState.APPROVED,
        ReviewerState.NEEDS_CHANGES,
        ReviewerState.REJECTED
    ],
    ReviewerState.APPROVED: [ReviewerState.IDLE],
    ReviewerState.NEEDS_CHANGES: [ReviewerState.IDLE],
    ReviewerState.REJECTED: [ReviewerState.IDLE],
}
