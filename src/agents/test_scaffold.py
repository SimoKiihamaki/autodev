"""
AutoDev Agent System - Basic Tests

Simple tests to verify the scaffold is correctly structured.
Run with: pytest test_scaffold.py -v
"""

import pytest
from src.agents.base import (
    BaseAgent,
    AgentRole,
    AgentState,
    TaskSpec,
    TaskResult,
    SubTask
)
from src.agents.states import (
    StateMachine,
    ManagerState,
    CoderState,
    ReviewerState,
    MANAGER_TRANSITIONS,
    CODER_TRANSITIONS,
    REVIEWER_TRANSITIONS
)
from src.agents.communication import (
    AgentMessage,
    MessageType,
    TaskAssignment,
    ReviewResult,
    Finding,
    MessageRouter
)


class TestStateMachines:
    """Test state machine functionality."""
    
    def test_manager_state_machine_init(self):
        """Test Manager state machine initializes correctly."""
        sm = StateMachine(
            initial_state=ManagerState.INIT,
            valid_transitions=MANAGER_TRANSITIONS
        )
        assert sm.current_state == ManagerState.INIT
    
    def test_manager_state_transitions(self):
        """Test valid Manager state transitions."""
        sm = StateMachine(
            initial_state=ManagerState.INIT,
            valid_transitions=MANAGER_TRANSITIONS
        )
        
        # INIT -> DECOMPOSE
        assert sm.can_transition_to(ManagerState.DECOMPOSE)
        sm.transition(ManagerState.DECOMPOSE)
        assert sm.current_state == ManagerState.DECOMPOSE
        
        # DECOMPOSE -> DISPATCH
        sm.transition(ManagerState.DISPATCH)
        assert sm.current_state == ManagerState.DISPATCH
        
        # DISPATCH -> MONITOR
        sm.transition(ManagerState.MONITOR)
        assert sm.current_state == ManagerState.MONITOR
    
    def test_invalid_transition(self):
        """Test that invalid transitions are rejected."""
        sm = StateMachine(
            initial_state=ManagerState.INIT,
            valid_transitions=MANAGER_TRANSITIONS
        )
        
        # INIT -> COMPLETE is invalid
        assert not sm.can_transition_to(ManagerState.COMPLETE)
        
        with pytest.raises(ValueError):
            sm.transition(ManagerState.COMPLETE)
    
    def test_coder_state_machine(self):
        """Test Coder state machine."""
        sm = StateMachine(
            initial_state=CoderState.IDLE,
            valid_transitions=CODER_TRANSITIONS
        )
        
        assert sm.current_state == CoderState.IDLE
        sm.transition(CoderState.ASSIGNED)
        sm.transition(CoderState.IMPLEMENTING)
        assert sm.current_state == CoderState.IMPLEMENTING
    
    def test_reviewer_state_machine(self):
        """Test Reviewer state machine."""
        sm = StateMachine(
            initial_state=ReviewerState.IDLE,
            valid_transitions=REVIEWER_TRANSITIONS
        )
        
        sm.transition(ReviewerState.REVIEWING)
        sm.transition(ReviewerState.APPROVED)
        assert sm.current_state == ReviewerState.APPROVED


class TestCommunication:
    """Test communication protocol."""
    
    def test_agent_message_creation(self):
        """Test message creation and serialization."""
        message = AgentMessage(
            sender=AgentRole.MANAGER,
            receiver=AgentRole.CODER,
            type=MessageType.TASK_ASSIGNMENT,
            payload={"task_id": "test-123"}
        )
        
        assert message.sender == AgentRole.MANAGER
        assert message.receiver == AgentRole.CODER
        
        # Test serialization
        msg_dict = message.to_dict()
        assert msg_dict["sender"] == "manager"
        assert msg_dict["receiver"] == "coder"
    
    def test_message_router(self):
        """Test message routing."""
        router = MessageRouter()
        
        message = AgentMessage(
            sender=AgentRole.MANAGER,
            receiver=AgentRole.CODER,
            type=MessageType.TASK_ASSIGNMENT,
            payload={"test": "data"}
        )
        
        router.send(message)
        assert router.get_queue_length(AgentRole.CODER) == 1
        
        received = router.receive(AgentRole.CODER)
        assert received is not None
        assert received.type == MessageType.TASK_ASSIGNMENT
    
    def test_task_assignment(self):
        """Test task assignment structure."""
        assignment = TaskAssignment(
            task_id="task-1",
            task_type="implement",
            priority="high",
            specification="Add feature X"
        )
        
        data = assignment.to_dict()
        assert data["task_id"] == "task-1"
        assert data["priority"] == "high"
    
    def test_review_result(self):
        """Test review result structure."""
        finding = Finding(
            category="security",
            severity="major",
            file="src/auth.py",
            line=42,
            description="Potential SQL injection",
            recommendation="Use parameterized queries"
        )
        
        review = ReviewResult(
            task_id="task-1",
            verdict="needs_changes",
            findings=[finding],
            summary="1 major issue found"
        )
        
        data = review.to_dict()
        assert data["verdict"] == "needs_changes"
        assert len(data["findings"]) == 1


class TestDataStructures:
    """Test data structures."""
    
    def test_task_spec(self):
        """Test TaskSpec creation."""
        spec = TaskSpec(
            task_type="implement",
            specification="Add authentication",
            target_files=["src/auth.py"],
            constraints={"preserve_api": True}
        )
        
        assert spec.task_type == "implement"
        assert len(spec.target_files) == 1
        assert spec.timeout_seconds == 300
    
    def test_task_result(self):
        """Test TaskResult creation."""
        result = TaskResult(
            task_id="task-1",
            status="completed",
            files_modified=["src/auth.py"]
        )
        
        assert result.status == "completed"
        assert "src/auth.py" in result.files_modified
    
    def test_subtask(self):
        """Test SubTask creation."""
        subtask = SubTask(
            parent_task_id="parent-1",
            name="Implement login",
            task_type="implement",
            priority="high",
            assigned_to=AgentRole.CODER
        )
        
        assert subtask.priority == "high"
        assert subtask.assigned_to == AgentRole.CODER


class TestAgentRoles:
    """Test agent role enumeration."""
    
    def test_all_roles_exist(self):
        """Verify all expected roles are defined."""
        roles = [AgentRole.MANAGER, AgentRole.CODER, AgentRole.REVIEWER, AgentRole.TESTER]
        
        for role in roles:
            assert isinstance(role, AgentRole)
            assert isinstance(role.value, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
