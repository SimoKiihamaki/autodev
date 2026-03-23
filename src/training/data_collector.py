"""
Training Data Collector for AutoDev RL Training

This module provides execution trace collection from SWE-bench runs for
reinforcement learning training. It captures complete execution histories
including LLM prompts, responses, tool calls, and outcomes.

Usage:
    from training.data_collector import TrainingDataCollector, DataCollectionConfig
    
    config = DataCollectionConfig(
        output_dir="~/.autodev/training_data",
        max_traces_per_task=10,
        include_failed_attempts=True
    )
    
    collector = TrainingDataCollector(config)
    
    # Collect from SWE-bench harness
    await collector.collect_from_evaluation(
        harness=SWEBenchHarness(...),
        num_tasks=100
    )
"""

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from enum import Enum
import hashlib

# Optional dependencies
try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    PARQUET_AVAILABLE = True
except ImportError:
    PARQUET_AVAILABLE = False

logger = logging.getLogger(__name__)


class TraceStatus(Enum):
    """Status of an execution trace."""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class TraceStep:
    """
    A single step in the execution trace.
    
    Represents one iteration of the agent loop, including
    the LLM call and any tool invocations.
    """
    step_number: int
    timestamp: str
    
    # LLM interaction
    prompt: str
    response: str
    model: str = ""
    tokens_used: Dict[str, int] = field(default_factory=dict)
    
    # Tool calls made in this step
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    
    # Timing
    latency_seconds: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TraceStep":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class CodeChange:
    """
    Represents a code change made during execution.
    """
    file_path: str
    change_type: str  # "create", "modify", "delete"
    original_content: Optional[str] = None
    new_content: Optional[str] = None
    diff: Optional[str] = None
    language: str = "python"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CodeChange":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class ExecutionTrace:
    """
    Complete execution history of a task attempt.
    
    Captures all information needed for GRPO training including:
    - Input context (problem statement, repo context)
    - Execution history (messages, tool calls, code changes)
    - Outcome (success/failure, test results)
    - Computed reward (set after reward calculation)
    """
    trace_id: str
    task_id: str
    timestamp: str
    
    # Input
    problem_statement: str
    repo_context: Dict[str, Any] = field(default_factory=dict)
    
    # Execution
    steps: List[TraceStep] = field(default_factory=list)
    code_changes: List[CodeChange] = field(default_factory=list)
    
    # Outcome
    status: TraceStatus = TraceStatus.FAILED
    tests_passed: List[str] = field(default_factory=list)
    tests_failed: List[str] = field(default_factory=list)
    execution_time_seconds: float = 0.0
    iterations: int = 0
    error: Optional[str] = None
    
    # For GRPO training
    prompt: str = ""  # The input prompt for the model
    completion: str = ""  # The generated code/solution
    reward: float = 0.0  # Computed reward (set by RewardCalculator)
    
    # Metadata
    model: str = ""
    total_tokens: Dict[str, int] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Generate trace_id if not provided."""
        if not self.trace_id:
            self.trace_id = self._generate_trace_id()
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
    
    def _generate_trace_id(self) -> str:
        """Generate a unique trace ID."""
        return f"trace_{self.task_id}_{uuid.uuid4().hex[:8]}"
    
    def add_step(self, step: TraceStep) -> None:
        """Add a step to the execution trace."""
        self.steps.append(step)
        self.iterations = len(self.steps)
    
    def add_code_change(self, change: CodeChange) -> None:
        """Add a code change to the trace."""
        self.code_changes.append(change)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "trace_id": self.trace_id,
            "task_id": self.task_id,
            "timestamp": self.timestamp,
            "problem_statement": self.problem_statement,
            "repo_context": self.repo_context,
            "steps": [s.to_dict() for s in self.steps],
            "code_changes": [c.to_dict() for c in self.code_changes],
            "status": self.status.value,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "execution_time_seconds": self.execution_time_seconds,
            "iterations": self.iterations,
            "error": self.error,
            "prompt": self.prompt,
            "completion": self.completion,
            "reward": self.reward,
            "model": self.model,
            "total_tokens": self.total_tokens,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionTrace":
        """Create from dictionary."""
        # Handle enum conversion
        if isinstance(data.get("status"), str):
            data["status"] = TraceStatus(data["status"])
        
        # Handle nested objects
        if "steps" in data:
            data["steps"] = [TraceStep.from_dict(s) for s in data["steps"]]
        if "code_changes" in data:
            data["code_changes"] = [CodeChange.from_dict(c) for c in data["code_changes"]]
        
        return cls(**data)
    
    def get_formatted_prompt(self) -> str:
        """
        Get the formatted prompt for GRPO training.
        
        Combines problem statement and repo context into
        a training-ready prompt format.
        """
        if self.prompt:
            return self.prompt
        
        # Build prompt from components
        parts = [f"# Task: {self.task_id}\n"]
        parts.append(f"## Problem\n{self.problem_statement}\n")
        
        if self.repo_context:
            parts.append("\n## Repository Context\n")
            for key, value in self.repo_context.items():
                if isinstance(value, str) and len(value) < 1000:
                    parts.append(f"- {key}: {value}\n")
        
        return "".join(parts)
    
    def get_formatted_completion(self) -> str:
        """
        Get the formatted completion for GRPO training.
        
        Extracts the final code changes as the completion.
        """
        if self.completion:
            return self.completion
        
        # Build completion from code changes
        if not self.code_changes:
            return ""
        
        parts = []
        for change in self.code_changes:
            if change.change_type in ("create", "modify"):
                parts.append(f"# File: {change.file_path}\n")
                if change.new_content:
                    parts.append(change.new_content)
                    parts.append("\n")
        
        return "".join(parts)


@dataclass
class DataCollectionConfig:
    """Configuration for training data collection."""
    output_dir: str = "~/.autodev/training_data"
    max_traces_per_task: int = 10
    include_failed_attempts: bool = True
    include_partial_success: bool = True
    storage_format: str = "jsonl"  # "jsonl" or "parquet"
    compress_output: bool = True
    max_trace_size_mb: float = 10.0
    flush_interval: int = 100  # Flush to disk every N traces
    
    def __post_init__(self):
        """Expand output directory path."""
        self.output_dir = os.path.expanduser(self.output_dir)


class TrainingDataCollector:
    """
    Collects execution traces from AutoDev pipeline runs for training.
    
    This class provides:
    - Trace capture from pipeline execution
    - Efficient storage (parquet/jsonl)
    - Filtering by outcome, task type, etc.
    - Integration with SWE-bench harness
    
    Example:
        collector = TrainingDataCollector(
            output_dir="~/.autodev/training_data",
            max_traces_per_task=10
        )
        
        # Start a trace
        trace = collector.start_trace(
            task_id="django__django-12345",
            problem_statement="Fix bug in ORM...",
            repo_context={"repo": "django/django"}
        )
        
        # Record steps
        collector.record_step(
            trace=trace,
            prompt="...",
            response="...",
            tool_calls=[...]
        )
        
        # Finalize trace
        collector.finalize_trace(
            trace=trace,
            success=True,
            tests_passed=["test_foo", "test_bar"]
        )
    """
    
    def __init__(self, config: Optional[DataCollectionConfig] = None):
        """
        Initialize the training data collector.
        
        Args:
            config: Collection configuration. Uses defaults if not provided.
        """
        self.config = config or DataCollectionConfig()
        self._current_traces: Dict[str, ExecutionTrace] = {}
        self._collected_traces: List[ExecutionTrace] = []
        self._trace_counts: Dict[str, int] = {}  # task_id -> count
        self._is_collecting = False
        
        # Ensure output directory exists
        self.output_path = Path(self.config.output_dir)
        self.output_path.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        self.traces_path = self.output_path / "traces"
        self.traces_path.mkdir(exist_ok=True)
        
        logger.info(f"TrainingDataCollector initialized with output_dir={self.output_path}")
    
    def start_trace(
        self,
        task_id: str,
        problem_statement: str,
        repo_context: Optional[Dict[str, Any]] = None,
        model: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> ExecutionTrace:
        """
        Start a new execution trace.
        
        Args:
            task_id: Unique task identifier
            problem_statement: The problem to solve
            repo_context: Repository context information
            model: LLM model being used
            metadata: Additional metadata
            
        Returns:
            New ExecutionTrace instance
        """
        trace = ExecutionTrace(
            trace_id="",
            task_id=task_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            problem_statement=problem_statement,
            repo_context=repo_context or {},
            model=model,
            metadata=metadata or {}
        )
        
        self._current_traces[trace.trace_id] = trace
        self._is_collecting = True
        
        logger.debug(f"Started trace {trace.trace_id} for task {task_id}")
        return trace
    
    def record_step(
        self,
        trace: ExecutionTrace,
        prompt: str,
        response: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        tool_results: Optional[List[Dict[str, Any]]] = None,
        tokens_used: Optional[Dict[str, int]] = None,
        latency_seconds: float = 0.0,
        model: str = ""
    ) -> None:
        """
        Record a step in the execution trace.
        
        Args:
            trace: The execution trace to update
            prompt: The LLM prompt
            response: The LLM response
            tool_calls: List of tool calls made
            tool_results: List of tool results received
            tokens_used: Token usage information
            latency_seconds: Time taken for this step
            model: Model used for this step
        """
        step = TraceStep(
            step_number=len(trace.steps) + 1,
            timestamp=datetime.now(timezone.utc).isoformat(),
            prompt=prompt,
            response=response,
            model=model or trace.model,
            tokens_used=tokens_used or {},
            tool_calls=tool_calls or [],
            tool_results=tool_results or [],
            latency_seconds=latency_seconds
        )
        
        trace.add_step(step)
        
        # Update total tokens
        if tokens_used:
            for key, value in tokens_used.items():
                trace.total_tokens[key] = trace.total_tokens.get(key, 0) + value
    
    def record_code_change(
        self,
        trace: ExecutionTrace,
        file_path: str,
        change_type: str,
        original_content: Optional[str] = None,
        new_content: Optional[str] = None,
        diff: Optional[str] = None,
        language: str = "python"
    ) -> None:
        """
        Record a code change in the execution trace.
        
        Args:
            trace: The execution trace to update
            file_path: Path to the modified file
            change_type: Type of change ("create", "modify", "delete")
            original_content: Original file content
            new_content: New file content
            diff: Git diff for the change
            language: Programming language
        """
        change = CodeChange(
            file_path=file_path,
            change_type=change_type,
            original_content=original_content,
            new_content=new_content,
            diff=diff,
            language=language
        )
        
        trace.add_code_change(change)
        logger.debug(f"Recorded code change for {file_path} in trace {trace.trace_id}")
    
    def finalize_trace(
        self,
        trace: ExecutionTrace,
        status: TraceStatus,
        tests_passed: Optional[List[str]] = None,
        tests_failed: Optional[List[str]] = None,
        execution_time_seconds: float = 0.0,
        error: Optional[str] = None
    ) -> bool:
        """
        Finalize an execution trace and store it.
        
        Args:
            trace: The execution trace to finalize
            status: Final status of the execution
            tests_passed: List of passing tests
            tests_failed: List of failing tests
            execution_time_seconds: Total execution time
            error: Error message if failed
            
        Returns:
            True if trace was stored, False if filtered out
        """
        trace.status = status
        trace.tests_passed = tests_passed or []
        trace.tests_failed = tests_failed or []
        trace.execution_time_seconds = execution_time_seconds
        trace.error = error
        
        # Set prompt and completion for GRPO
        trace.prompt = trace.get_formatted_prompt()
        trace.completion = trace.get_formatted_completion()
        
        # Check if we should store this trace
        if not self._should_store_trace(trace):
            logger.debug(f"Skipping trace {trace.trace_id} due to filtering")
            return False
        
        # Check trace count limit
        task_count = self._trace_counts.get(trace.task_id, 0)
        if task_count >= self.config.max_traces_per_task:
            logger.debug(f"Max traces reached for task {trace.task_id}")
            return False
        
        # Store the trace
        self._collected_traces.append(trace)
        self._trace_counts[trace.task_id] = task_count + 1
        
        # Remove from current traces
        if trace.trace_id in self._current_traces:
            del self._current_traces[trace.trace_id]
        
        logger.info(f"Finalized trace {trace.trace_id} with status {status.value}")
        
        # Flush if needed
        if len(self._collected_traces) >= self.config.flush_interval:
            self.flush()
        
        return True
    
    def _should_store_trace(self, trace: ExecutionTrace) -> bool:
        """Check if a trace should be stored based on configuration."""
        # Always store successful traces
        if trace.status == TraceStatus.SUCCESS:
            return True
        
        # Check configuration for other statuses
        if trace.status == TraceStatus.FAILED and not self.config.include_failed_attempts:
            return False
        
        if trace.status == TraceStatus.PARTIAL and not self.config.include_partial_success:
            return False
        
        return True
    
    def get_trace(self, trace_id: str) -> Optional[ExecutionTrace]:
        """Get a trace by ID from current or collected traces."""
        if trace_id in self._current_traces:
            return self._current_traces[trace_id]
        
        for trace in self._collected_traces:
            if trace.trace_id == trace_id:
                return trace
        
        return None
    
    def get_collected_traces(
        self,
        status: Optional[TraceStatus] = None,
        task_id: Optional[str] = None,
        min_reward: Optional[float] = None,
        max_reward: Optional[float] = None
    ) -> List[ExecutionTrace]:
        """
        Get collected traces with optional filtering.
        
        Args:
            status: Filter by trace status
            task_id: Filter by task ID
            min_reward: Minimum reward threshold
            max_reward: Maximum reward threshold
            
        Returns:
            List of matching traces
        """
        traces = self._collected_traces
        
        if status:
            traces = [t for t in traces if t.status == status]
        
        if task_id:
            traces = [t for t in traces if t.task_id == task_id]
        
        if min_reward is not None:
            traces = [t for t in traces if t.reward >= min_reward]
        
        if max_reward is not None:
            traces = [t for t in traces if t.reward <= max_reward]
        
        return traces
    
    def flush(self) -> Path:
        """
        Flush collected traces to disk.
        
        Returns:
            Path to the output file
        """
        if not self._collected_traces:
            logger.debug("No traces to flush")
            return self.output_path
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        
        if self.config.storage_format == "parquet" and PARQUET_AVAILABLE:
            output_file = self._flush_parquet(timestamp)
        else:
            output_file = self._flush_jsonl(timestamp)
        
        # Clear collected traces
        count = len(self._collected_traces)
        self._collected_traces = []
        
        logger.info(f"Flushed {count} traces to {output_file}")
        return output_file
    
    def _flush_jsonl(self, timestamp: str) -> Path:
        """Flush traces to JSONL format."""
        filename = f"traces_{timestamp}.jsonl"
        if self.config.compress_output:
            filename += ".gz"
        
        output_file = self.traces_path / filename
        
        import gzip
        
        open_func = gzip.open if self.config.compress_output else open
        mode = "at" if self.config.compress_output else "a"
        
        with open_func(output_file, mode, encoding="utf-8") as f:
            for trace in self._collected_traces:
                f.write(json.dumps(trace.to_dict()) + "\n")
        
        return output_file
    
    def _flush_parquet(self, timestamp: str) -> Path:
        """Flush traces to Parquet format."""
        filename = f"traces_{timestamp}.parquet"
        output_file = self.traces_path / filename
        
        # Convert traces to table format
        records = [trace.to_dict() for trace in self._collected_traces]
        
        # Flatten nested structures for parquet
        flat_records = []
        for record in records:
            flat = {
                "trace_id": record["trace_id"],
                "task_id": record["task_id"],
                "timestamp": record["timestamp"],
                "problem_statement": record["problem_statement"],
                "status": record["status"],
                "execution_time_seconds": record["execution_time_seconds"],
                "iterations": record["iterations"],
                "error": record["error"],
                "prompt": record["prompt"],
                "completion": record["completion"],
                "reward": record["reward"],
                "model": record["model"],
                "num_tests_passed": len(record["tests_passed"]),
                "num_tests_failed": len(record["tests_failed"]),
                "num_code_changes": len(record["code_changes"]),
                "tests_passed": json.dumps(record["tests_passed"]),
                "tests_failed": json.dumps(record["tests_failed"]),
                "steps": json.dumps(record["steps"]),
                "code_changes": json.dumps(record["code_changes"]),
                "repo_context": json.dumps(record["repo_context"]),
                "total_tokens": json.dumps(record["total_tokens"]),
                "metadata": json.dumps(record["metadata"]),
            }
            flat_records.append(flat)
        
        # Create table and write
        table = pa.Table.from_pylist(flat_records)
        pq.write_table(table, output_file, compression="snappy")
        
        return output_file
    
    async def collect_from_evaluation(
        self,
        harness: "SWEBenchHarness",
        num_tasks: int = 100,
        subset: str = "lite",
        task_ids: Optional[List[str]] = None
    ) -> List[ExecutionTrace]:
        """
        Collect execution traces from a SWE-bench evaluation.
        
        Args:
            harness: SWE-bench harness instance
            num_tasks: Number of tasks to run
            subset: SWE-bench subset to use
            task_ids: Specific task IDs to run
            
        Returns:
            List of collected execution traces
        """
        logger.info(f"Starting data collection from {subset} subset")
        
        # Load tasks
        tasks = harness.load_tasks(
            subset=subset,
            num_tasks=num_tasks,
            task_ids=task_ids
        )
        
        logger.info(f"Loaded {len(tasks)} tasks for collection")
        
        # Run tasks and collect traces
        for i, task in enumerate(tasks):
            logger.info(f"Processing task {i+1}/{len(tasks)}: {task.instance_id}")
            
            # Start trace
            trace = self.start_trace(
                task_id=task.instance_id,
                problem_statement=task.problem_statement,
                repo_context={
                    "repo": task.repo,
                    "base_commit": task.base_commit,
                    "version": task.version,
                },
                model=harness.model,
                metadata={
                    "subset": subset,
                    "FAIL_TO_PASS": task.FAIL_TO_PASS,
                    "PASS_TO_PASS": task.PASS_TO_PASS,
                }
            )
            
            # Run task with trace capture
            try:
                task_workspace = harness.workspace / task.instance_id
                result = await harness.run_task(task, task_workspace)
                
                # Record code changes from patch
                if result.patch_generated:
                    self.record_code_change(
                        trace=trace,
                        file_path="patch.diff",
                        change_type="modify",
                        diff=result.patch_generated
                    )
                
                # Finalize trace
                status = TraceStatus.SUCCESS if result.status.value == "resolved" else TraceStatus.FAILED
                if result.status.value == "timeout":
                    status = TraceStatus.TIMEOUT
                elif result.status.value == "error":
                    status = TraceStatus.ERROR
                
                self.finalize_trace(
                    trace=trace,
                    status=status,
                    tests_passed=result.resolution_details.get("tests_passed", []),
                    tests_failed=result.resolution_details.get("tests_failed", []),
                    execution_time_seconds=result.execution_time_seconds,
                    error=result.error
                )
                
            except Exception as e:
                logger.error(f"Error collecting trace for {task.instance_id}: {e}")
                self.finalize_trace(
                    trace=trace,
                    status=TraceStatus.ERROR,
                    error=str(e)
                )
        
        # Final flush
        self.flush()
        
        logger.info(f"Data collection complete. Collected {len(self._collected_traces)} traces")
        return self._collected_traces
    
    def load_traces(self, path: Optional[Path] = None) -> List[ExecutionTrace]:
        """
        Load traces from disk.
        
        Args:
            path: Path to load from. Uses output_dir if not specified.
            
        Returns:
            List of loaded execution traces
        """
        path = path or self.output_path
        traces = []
        
        # Load from JSONL files
        for jsonl_file in path.glob("**/*.jsonl*"):
            import gzip
            
            open_func = gzip.open if str(jsonl_file).endswith(".gz") else open
            
            with open_func(jsonl_file, "rt", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        traces.append(ExecutionTrace.from_dict(data))
        
        # Load from Parquet files
        if PARQUET_AVAILABLE:
            for parquet_file in path.glob("**/*.parquet"):
                table = pq.read_table(parquet_file)
                for record in table.to_pylist():
                    # Reconstruct nested structures
                    record["tests_passed"] = json.loads(record.get("tests_passed", "[]"))
                    record["tests_failed"] = json.loads(record.get("tests_failed", "[]"))
                    record["steps"] = json.loads(record.get("steps", "[]"))
                    record["code_changes"] = json.loads(record.get("code_changes", "[]"))
                    record["repo_context"] = json.loads(record.get("repo_context", "{}"))
                    record["total_tokens"] = json.loads(record.get("total_tokens", "{}"))
                    record["metadata"] = json.loads(record.get("metadata", "{}"))
                    traces.append(ExecutionTrace.from_dict(record))
        
        logger.info(f"Loaded {len(traces)} traces from {path}")
        return traces
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about collected traces.
        
        Returns:
            Dictionary with collection statistics
        """
        traces = self._collected_traces
        
        if not traces:
            return {
                "total_traces": 0,
                "unique_tasks": 0,
            }
        
        # Count by status
        status_counts = {}
        for trace in traces:
            status = trace.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Calculate averages
        avg_iterations = sum(t.iterations for t in traces) / len(traces)
        avg_time = sum(t.execution_time_seconds for t in traces) / len(traces)
        avg_reward = sum(t.reward for t in traces) / len(traces)
        
        return {
            "total_traces": len(traces),
            "unique_tasks": len(set(t.task_id for t in traces)),
            "status_counts": status_counts,
            "avg_iterations": avg_iterations,
            "avg_execution_time_seconds": avg_time,
            "avg_reward": avg_reward,
            "total_tokens": sum(
                sum(t.total_tokens.values()) for t in traces
            ),
        }
    
    def export_for_training(
        self,
        output_path: Optional[Path] = None,
        format: str = "jsonl",
        min_reward: Optional[float] = None,
        include_unsuccessful: bool = False
    ) -> Path:
        """
        Export traces in a format suitable for GRPO training.
        
        Args:
            output_path: Output file path
            format: Output format ("jsonl" or "parquet")
            min_reward: Minimum reward threshold
            include_unsuccessful: Include unsuccessful traces
            
        Returns:
            Path to exported file
        """
        # Filter traces
        traces = self._collected_traces
        
        if min_reward is not None:
            traces = [t for t in traces if t.reward >= min_reward]
        
        if not include_unsuccessful:
            traces = [t for t in traces if t.status == TraceStatus.SUCCESS]
        
        if not traces:
            raise ValueError("No traces match the export criteria")
        
        # Set output path
        if output_path is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            output_path = self.output_path / f"training_data_{timestamp}.{format}"
        
        # Export
        if format == "parquet" and PARQUET_AVAILABLE:
            records = []
            for trace in traces:
                records.append({
                    "prompt": trace.prompt,
                    "completion": trace.completion,
                    "reward": trace.reward,
                    "task_id": trace.task_id,
                    "status": trace.status.value,
                })
            
            table = pa.Table.from_pylist(records)
            pq.write_table(table, output_path, compression="snappy")
        else:
            with open(output_path, "w", encoding="utf-8") as f:
                for trace in traces:
                    record = {
                        "prompt": trace.prompt,
                        "completion": trace.completion,
                        "reward": trace.reward,
                        "task_id": trace.task_id,
                        "status": trace.status.value,
                    }
                    f.write(json.dumps(record) + "\n")
        
        logger.info(f"Exported {len(traces)} traces to {output_path}")
        return output_path


# Convenience function for creating a collector
def create_collector(
    output_dir: str = "~/.autodev/training_data",
    **kwargs
) -> TrainingDataCollector:
    """
    Create a TrainingDataCollector with the given configuration.
    
    Args:
        output_dir: Directory for storing traces
        **kwargs: Additional configuration options
        
    Returns:
        Configured TrainingDataCollector instance
    """
    config = DataCollectionConfig(output_dir=output_dir, **kwargs)
    return TrainingDataCollector(config)
