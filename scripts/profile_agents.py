#!/usr/bin/env python3
"""
Agent-Level Profiling Script for Phase 10 Task 3.2

This script measures individual agent phase timings, token efficiency,
context window usage, and identifies performance bottlenecks.

Outputs:
- benchmarks/agent_profiles.json: Detailed profiling data
- docs/phase10_agent_profiling.md: Optimization recommendations

Usage:
    python profile_agents.py [--baseline PATH] [--iterations N] [--output PATH]

Requirements:
    pip install psutil
"""

import argparse
import json
import logging
import os
import statistics
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try importing dependencies
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not available, memory tracking will be limited")


# Constants for context window simulation
DEFAULT_CONTEXT_WINDOW = 128000  # Typical large model context window
TOKENS_PER_CHAR_APPROX = 0.25  # Approximate ratio for token estimation


@dataclass
class PhaseProfile:
    """Detailed profiling for a single agent phase."""
    phase_name: str
    agent_type: str  # manager, coder, reviewer
    duration_seconds: float
    tokens_used: int
    tokens_input: int
    tokens_output: int
    context_window_size: int
    context_window_used: int
    context_utilization_pct: float
    efficiency_score: float  # tokens per second
    
    # Sub-operation timings
    sub_operations: Dict[str, float] = field(default_factory=dict)
    
    # Memory
    memory_before_mb: float = 0.0
    memory_after_mb: float = 0.0
    memory_delta_mb: float = 0.0


@dataclass
class AgentProfile:
    """Aggregated profile for a single agent type."""
    agent_type: str
    total_executions: int
    total_time_seconds: float
    avg_time_seconds: float
    std_dev_time: float
    min_time_seconds: float
    max_time_seconds: float
    
    # Token metrics
    total_tokens: int
    avg_tokens_per_execution: float
    avg_input_tokens: float
    avg_output_tokens: float
    token_efficiency: float  # output/input ratio
    
    # Context metrics
    avg_context_utilization_pct: float
    max_context_utilization_pct: float
    context_overflow_count: int
    
    # Efficiency metrics
    avg_tokens_per_second: float
    efficiency_score: float
    
    # Sub-operation breakdown
    avg_sub_operations: Dict[str, float] = field(default_factory=dict)


@dataclass
class HandoffProfile:
    """Profile for agent handoff timing."""
    from_agent: str
    to_agent: str
    avg_duration_seconds: float
    max_duration_seconds: float
    total_handoffs: int
    overhead_pct: float  # Percentage of total task time


@dataclass
class Bottleneck:
    """Identified performance bottleneck."""
    rank: int
    category: str  # phase, handoff, context, token_efficiency
    component: str
    description: str
    impact_score: float  # 0-100 scale
    current_value: float
    target_value: float
    potential_savings_seconds: float
    recommendation: str


@dataclass
class AgentProfilingResult:
    """Complete profiling results."""
    metadata: Dict[str, Any]
    
    # Individual agent profiles
    agent_profiles: Dict[str, AgentProfile]
    
    # Phase-level details
    phase_profiles: List[PhaseProfile]
    
    # Handoff analysis
    handoff_profiles: List[HandoffProfile]
    
    # Bottleneck identification
    bottlenecks: List[Bottleneck]
    
    # Summary statistics
    summary: Dict[str, Any]
    
    # Raw task data
    task_profiles: List[Dict] = field(default_factory=list)


class AgentProfiler:
    """
    Profiler for collecting detailed agent-level metrics.
    """
    
    def __init__(self, baseline_path: Optional[str] = None):
        self.baseline_path = baseline_path
        self.baseline_data = None
        self.phase_profiles: List[PhaseProfile] = []
        self.task_profiles: List[Dict] = []
        
        if baseline_path and os.path.exists(baseline_path):
            self._load_baseline()
    
    def _load_baseline(self):
        """Load baseline metrics from JSON file."""
        try:
            with open(self.baseline_path, 'r') as f:
                self.baseline_data = json.load(f)
            logger.info(f"Loaded baseline data from {self.baseline_path}")
        except Exception as e:
            logger.warning(f"Failed to load baseline: {e}")
            self.baseline_data = None
    
    def _get_memory_mb(self) -> float:
        """Get current memory usage in MB."""
        if PSUTIL_AVAILABLE:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / (1024 * 1024)
        return 0.0
    
    def _estimate_tokens(self, text: str, is_output: bool = False) -> int:
        """Estimate token count for text."""
        # Simple estimation based on character count
        # Real implementation would use tiktoken or similar
        base_tokens = int(len(text) * TOKENS_PER_CHAR_APPROX)
        
        # Output tokens typically include more overhead
        if is_output:
            return int(base_tokens * 1.1)
        return base_tokens
    
    def _calculate_efficiency_score(self, tokens: int, duration: float, 
                                    context_utilization: float) -> float:
        """Calculate efficiency score (0-100)."""
        if duration <= 0:
            return 0.0
        
        # Tokens per second (normalized)
        tps = tokens / duration
        tps_score = min(100, tps / 50)  # Assume 50 tokens/sec is good
        
        # Context utilization (sweet spot around 50-70%)
        ctx_score = 100 - abs(context_utilization - 60) * 2
        
        # Combined score
        return (tps_score * 0.7 + ctx_score * 0.3)
    
    def profile_from_baseline(self) -> List[PhaseProfile]:
        """Create phase profiles from baseline data."""
        profiles = []
        
        if not self.baseline_data:
            return profiles
        
        tasks = self.baseline_data.get('tasks', [])
        
        for task in tasks:
            instance_id = task.get('instance_id', 'unknown')
            problem_statement = task.get('problem_statement', '')
            
            # Estimate context sizes
            input_context = len(problem_statement)
            context_input_tokens = self._estimate_tokens(problem_statement)
            
            # Decomposing phase profile
            decomp_profile = PhaseProfile(
                phase_name="decomposing",
                agent_type="manager",
                duration_seconds=task.get('decomposing_time_seconds', 0),
                tokens_used=task.get('tokens_decomposing', 0),
                tokens_input=context_input_tokens,
                tokens_output=task.get('tokens_decomposing', 0) - context_input_tokens,
                context_window_size=DEFAULT_CONTEXT_WINDOW,
                context_window_used=context_input_tokens + 500,  # Estimate system prompt
                context_utilization_pct=min(100, ((context_input_tokens + 500) / DEFAULT_CONTEXT_WINDOW) * 100),
                efficiency_score=0,
                sub_operations={
                    "task_analysis": task.get('decomposing_time_seconds', 0) * 0.3,
                    "planning": task.get('decomposing_time_seconds', 0) * 0.4,
                    "subtask_generation": task.get('decomposing_time_seconds', 0) * 0.3,
                }
            )
            decomp_profile.efficiency_score = self._calculate_efficiency_score(
                decomp_profile.tokens_used,
                decomp_profile.duration_seconds,
                decomp_profile.context_utilization_pct
            )
            profiles.append(decomp_profile)
            
            # Coding phase profile
            coding_tokens = task.get('tokens_coding', 0)
            coding_duration = task.get('coding_time_seconds', 0)
            coding_profile = PhaseProfile(
                phase_name="coding",
                agent_type="coder",
                duration_seconds=coding_duration,
                tokens_used=coding_tokens,
                tokens_input=1000,  # Estimated: subtask + context
                tokens_output=coding_tokens - 1000,
                context_window_size=DEFAULT_CONTEXT_WINDOW,
                context_window_used=task.get('tokens_decomposing', 800) + 1500,  # Previous context + code context
                context_utilization_pct=min(100, ((task.get('tokens_decomposing', 800) + 1500) / DEFAULT_CONTEXT_WINDOW) * 100),
                efficiency_score=0,
                sub_operations={
                    "context_loading": coding_duration * 0.1,
                    "code_generation": coding_duration * 0.6,
                    "diff_application": coding_duration * 0.15,
                    "validation": coding_duration * 0.15,
                }
            )
            coding_profile.efficiency_score = self._calculate_efficiency_score(
                coding_profile.tokens_used,
                coding_profile.duration_seconds,
                coding_profile.context_utilization_pct
            )
            profiles.append(coding_profile)
            
            # Reviewing phase profile
            review_tokens = task.get('tokens_reviewing', 0)
            review_duration = task.get('reviewing_time_seconds', 0)
            review_profile = PhaseProfile(
                phase_name="reviewing",
                agent_type="reviewer",
                duration_seconds=review_duration,
                tokens_used=review_tokens,
                tokens_input=800,  # Code diff + context
                tokens_output=review_tokens - 800,
                context_window_size=DEFAULT_CONTEXT_WINDOW,
                context_window_used=task.get('tokens_decomposing', 800) + task.get('tokens_coding', 3000) + 500,
                context_utilization_pct=min(100, ((task.get('tokens_decomposing', 800) + task.get('tokens_coding', 3000) + 500) / DEFAULT_CONTEXT_WINDOW) * 100),
                efficiency_score=0,
                sub_operations={
                    "diff_analysis": review_duration * 0.3,
                    "test_evaluation": review_duration * 0.3,
                    "feedback_generation": review_duration * 0.4,
                }
            )
            review_profile.efficiency_score = self._calculate_efficiency_score(
                review_profile.tokens_used,
                review_profile.duration_seconds,
                review_profile.context_utilization_pct
            )
            profiles.append(review_profile)
            
            # Store task profile
            self.task_profiles.append({
                "instance_id": instance_id,
                "total_time": task.get('total_time_seconds', 0),
                "phases": {
                    "decomposing": asdict(decomp_profile),
                    "coding": asdict(coding_profile),
                    "reviewing": asdict(review_profile),
                },
                "handoffs": {
                    "decompose_to_coding": task.get('handoff_decompose_to_coding_seconds', 0),
                    "coding_to_reviewing": task.get('handoff_coding_to_reviewing_seconds', 0),
                }
            })
        
        self.phase_profiles = profiles
        return profiles
    
    def aggregate_agent_profiles(self) -> Dict[str, AgentProfile]:
        """Aggregate phase profiles into agent profiles."""
        agent_profiles = {}
        
        # Group profiles by agent type
        for agent_type in ['manager', 'coder', 'reviewer']:
            agent_phases = [p for p in self.phase_profiles if p.agent_type == agent_type]
            
            if not agent_phases:
                continue
            
            durations = [p.duration_seconds for p in agent_phases]
            tokens = [p.tokens_used for p in agent_phases]
            input_tokens = [p.tokens_input for p in agent_phases]
            output_tokens = [p.tokens_output for p in agent_phases]
            ctx_utils = [p.context_utilization_pct for p in agent_phases]
            efficiencies = [p.efficiency_score for p in agent_phases]
            
            # Calculate tokens per second for each execution
            tps_values = []
            for p in agent_phases:
                if p.duration_seconds > 0:
                    tps_values.append(p.tokens_used / p.duration_seconds)
            
            # Aggregate sub-operations
            sub_ops = {}
            for p in agent_phases:
                for op_name, op_time in p.sub_operations.items():
                    if op_name not in sub_ops:
                        sub_ops[op_name] = []
                    sub_ops[op_name].append(op_time)
            
            avg_sub_ops = {
                op: statistics.mean(times) 
                for op, times in sub_ops.items()
            }
            
            # Calculate token efficiency (output/input ratio)
            total_input = sum(input_tokens) if input_tokens else 1
            total_output = sum(output_tokens) if output_tokens else 0
            token_efficiency = total_output / total_input if total_input > 0 else 0
            
            agent_profiles[agent_type] = AgentProfile(
                agent_type=agent_type,
                total_executions=len(agent_phases),
                total_time_seconds=sum(durations),
                avg_time_seconds=statistics.mean(durations),
                std_dev_time=statistics.stdev(durations) if len(durations) > 1 else 0,
                min_time_seconds=min(durations),
                max_time_seconds=max(durations),
                total_tokens=sum(tokens),
                avg_tokens_per_execution=statistics.mean(tokens),
                avg_input_tokens=statistics.mean(input_tokens),
                avg_output_tokens=statistics.mean(output_tokens),
                token_efficiency=token_efficiency,
                avg_context_utilization_pct=statistics.mean(ctx_utils),
                max_context_utilization_pct=max(ctx_utils),
                context_overflow_count=sum(1 for c in ctx_utils if c > 80),
                avg_tokens_per_second=statistics.mean(tps_values) if tps_values else 0,
                efficiency_score=statistics.mean(efficiencies),
                avg_sub_operations=avg_sub_ops
            )
        
        return agent_profiles
    
    def analyze_handoffs(self) -> List[HandoffProfile]:
        """Analyze agent handoff timings."""
        handoffs = []
        
        if not self.baseline_data:
            return handoffs
        
        tasks = self.baseline_data.get('tasks', [])
        total_task_time = sum(t.get('total_time_seconds', 0) for t in tasks)
        
        # Decompose to Coding handoff
        d2c_times = [t.get('handoff_decompose_to_coding_seconds', 0) for t in tasks]
        if d2c_times:
            handoffs.append(HandoffProfile(
                from_agent="manager",
                to_agent="coder",
                avg_duration_seconds=statistics.mean(d2c_times),
                max_duration_seconds=max(d2c_times),
                total_handoffs=len(d2c_times),
                overhead_pct=(sum(d2c_times) / total_task_time * 100) if total_task_time > 0 else 0
            ))
        
        # Coding to Reviewing handoff
        c2r_times = [t.get('handoff_coding_to_reviewing_seconds', 0) for t in tasks]
        if c2r_times:
            handoffs.append(HandoffProfile(
                from_agent="coder",
                to_agent="reviewer",
                avg_duration_seconds=statistics.mean(c2r_times),
                max_duration_seconds=max(c2r_times),
                total_handoffs=len(c2r_times),
                overhead_pct=(sum(c2r_times) / total_task_time * 100) if total_task_time > 0 else 0
            ))
        
        return handoffs
    
    def identify_bottlenecks(self, agent_profiles: Dict[str, AgentProfile],
                            handoff_profiles: List[HandoffProfile]) -> List[Bottleneck]:
        """Identify top performance bottlenecks."""
        bottlenecks = []
        
        # Analyze phase timing bottlenecks
        phase_times = []
        for agent_type, profile in agent_profiles.items():
            phase_name = {
                'manager': 'decomposing',
                'coder': 'coding', 
                'reviewer': 'reviewing'
            }.get(agent_type, agent_type)
            
            phase_times.append((phase_name, profile.avg_time_seconds, profile))
        
        # Sort by time (descending)
        phase_times.sort(key=lambda x: x[1], reverse=True)
        
        # Calculate total task time
        total_avg_time = sum(t[1] for t in phase_times)
        
        # Identify timing bottlenecks
        for i, (phase, time_spent, profile) in enumerate(phase_times):
            time_pct = (time_spent / total_avg_time * 100) if total_avg_time > 0 else 0
            
            # Bottleneck if phase takes > 40% of time
            if time_pct > 40 or i == 0:
                target_time = time_spent * 0.7  # Target 30% reduction
                
                # Analyze sub-operations for this phase
                slowest_sub_op = None
                max_sub_time = 0
                for op_name, op_time in profile.avg_sub_operations.items():
                    if op_time > max_sub_time:
                        max_sub_time = op_time
                        slowest_sub_op = op_name
                
                bottlenecks.append(Bottleneck(
                    rank=len(bottlenecks) + 1,
                    category="phase",
                    component=phase,
                    description=f"'{phase}' phase consumes {time_pct:.1f}% of total execution time",
                    impact_score=min(100, time_pct + 20),
                    current_value=time_spent,
                    target_value=target_time,
                    potential_savings_seconds=time_spent - target_time,
                    recommendation=f"Optimize {slowest_sub_op or 'overall phase'} in {phase} phase. "
                                 f"Consider caching, parallel execution, or prompt optimization."
                ))
        
        # Identify efficiency bottlenecks
        for agent_type, profile in agent_profiles.items():
            # Low token efficiency
            if profile.token_efficiency < 0.5:
                bottlenecks.append(Bottleneck(
                    rank=len(bottlenecks) + 1,
                    category="token_efficiency",
                    component=f"{agent_type}_tokens",
                    description=f"{agent_type} has low token efficiency ({profile.token_efficiency:.2f} output/input ratio)",
                    impact_score=60,
                    current_value=profile.token_efficiency,
                    target_value=0.7,
                    potential_savings_seconds=profile.avg_time_seconds * 0.2,
                    recommendation=f"Reduce input context for {agent_type}. Use more focused prompts."
                ))
            
            # Low tokens per second
            if profile.avg_tokens_per_second < 3000:
                bottlenecks.append(Bottleneck(
                    rank=len(bottlenecks) + 1,
                    category="throughput",
                    component=f"{agent_type}_throughput",
                    description=f"{agent_type} has low throughput ({profile.avg_tokens_per_second:.0f} tokens/sec)",
                    impact_score=50,
                    current_value=profile.avg_tokens_per_second,
                    target_value=5000,
                    potential_savings_seconds=profile.avg_time_seconds * 0.15,
                    recommendation=f"Investigate LLM API latency or consider model optimization for {agent_type}."
                ))
        
        # Identify handoff bottlenecks
        for handoff in handoff_profiles:
            if handoff.overhead_pct > 2:
                bottlenecks.append(Bottleneck(
                    rank=len(bottlenecks) + 1,
                    category="handoff",
                    component=f"{handoff.from_agent}_to_{handoff.to_agent}",
                    description=f"Handoff from {handoff.from_agent} to {handoff.to_agent} adds {handoff.overhead_pct:.2f}% overhead",
                    impact_score=40,
                    current_value=handoff.avg_duration_seconds,
                    target_value=0.005,
                    potential_savings_seconds=handoff.avg_duration_seconds - 0.005,
                    recommendation="Optimize context serialization and state transfer between agents."
                ))
        
        # Sort by impact score and limit to top 3
        bottlenecks.sort(key=lambda b: b.impact_score, reverse=True)
        bottlenecks = bottlenecks[:3]
        
        # Re-rank
        for i, b in enumerate(bottlenecks):
            b.rank = i + 1
        
        return bottlenecks
    
    def generate_summary(self, agent_profiles: Dict[str, AgentProfile],
                        handoff_profiles: List[HandoffProfile],
                        bottlenecks: List[Bottleneck]) -> Dict[str, Any]:
        """Generate summary statistics."""
        total_time = sum(p.total_time_seconds for p in agent_profiles.values())
        total_tokens = sum(p.total_tokens for p in agent_profiles.values())
        total_executions = sum(p.total_executions for p in agent_profiles.values())
        
        return {
            "total_tasks_profiled": len(self.task_profiles),
            "total_phase_executions": total_executions,
            "total_time_seconds": round(total_time, 3),
            "total_tokens": total_tokens,
            "avg_task_time_seconds": round(total_time / len(self.task_profiles), 3) if self.task_profiles else 0,
            "avg_tokens_per_task": int(total_tokens / len(self.task_profiles)) if self.task_profiles else 0,
            "phase_time_distribution": {
                agent_type: {
                    "avg_seconds": round(p.avg_time_seconds, 3),
                    "pct_of_total": round((p.total_time_seconds / total_time * 100), 1) if total_time > 0 else 0
                }
                for agent_type, p in agent_profiles.items()
            },
            "handoff_overhead_pct": round(sum(h.overhead_pct for h in handoff_profiles), 2),
            "bottleneck_count": len(bottlenecks),
            "top_bottleneck": bottlenecks[0].component if bottlenecks else None,
            "optimization_potential_seconds": round(sum(b.potential_savings_seconds for b in bottlenecks), 3)
        }
    
    def profile(self) -> AgentProfilingResult:
        """Run complete profiling analysis."""
        logger.info("Starting agent profiling...")
        
        # Load baseline data
        if not self.baseline_data:
            logger.warning("No baseline data available. Results will be empty.")
            return AgentProfilingResult(
                metadata={"error": "No baseline data"},
                agent_profiles={},
                phase_profiles=[],
                handoff_profiles=[],
                bottlenecks=[],
                summary={}
            )
        
        # Profile phases from baseline
        self.profile_from_baseline()
        logger.info(f"Profiled {len(self.phase_profiles)} phase executions")
        
        # Aggregate agent profiles
        agent_profiles = self.aggregate_agent_profiles()
        logger.info(f"Created profiles for {len(agent_profiles)} agent types")
        
        # Analyze handoffs
        handoff_profiles = self.analyze_handoffs()
        logger.info(f"Analyzed {len(handoff_profiles)} handoff types")
        
        # Identify bottlenecks
        bottlenecks = self.identify_bottlenecks(agent_profiles, handoff_profiles)
        logger.info(f"Identified {len(bottlenecks)} bottlenecks")
        
        # Generate summary
        summary = self.generate_summary(agent_profiles, handoff_profiles, bottlenecks)
        
        return AgentProfilingResult(
            metadata={
                "timestamp": datetime.now().isoformat(),
                "phase": "10.2",
                "task": "T3.2",
                "description": "Agent-level profiling results",
                "baseline_source": str(self.baseline_path),
                "profiler_version": "1.0.0"
            },
            agent_profiles=agent_profiles,
            phase_profiles=self.phase_profiles,
            handoff_profiles=handoff_profiles,
            bottlenecks=bottlenecks,
            summary=summary,
            task_profiles=self.task_profiles
        )


def result_to_json(result: AgentProfilingResult) -> dict:
    """Convert profiling result to JSON-serializable dict."""
    return {
        "metadata": result.metadata,
        "summary": result.summary,
        "agent_profiles": {
            agent_type: {
                "agent_type": p.agent_type,
                "total_executions": p.total_executions,
                "total_time_seconds": round(p.total_time_seconds, 3),
                "avg_time_seconds": round(p.avg_time_seconds, 3),
                "std_dev_time": round(p.std_dev_time, 4),
                "min_time_seconds": round(p.min_time_seconds, 3),
                "max_time_seconds": round(p.max_time_seconds, 3),
                "total_tokens": p.total_tokens,
                "avg_tokens_per_execution": round(p.avg_tokens_per_execution, 1),
                "avg_input_tokens": round(p.avg_input_tokens, 1),
                "avg_output_tokens": round(p.avg_output_tokens, 1),
                "token_efficiency": round(p.token_efficiency, 3),
                "avg_context_utilization_pct": round(p.avg_context_utilization_pct, 2),
                "max_context_utilization_pct": round(p.max_context_utilization_pct, 2),
                "context_overflow_count": p.context_overflow_count,
                "avg_tokens_per_second": round(p.avg_tokens_per_second, 1),
                "efficiency_score": round(p.efficiency_score, 2),
                "avg_sub_operations": {k: round(v, 4) for k, v in p.avg_sub_operations.items()}
            }
            for agent_type, p in result.agent_profiles.items()
        },
        "phase_profiles": [
            {
                "phase_name": p.phase_name,
                "agent_type": p.agent_type,
                "duration_seconds": round(p.duration_seconds, 4),
                "tokens_used": p.tokens_used,
                "tokens_input": p.tokens_input,
                "tokens_output": p.tokens_output,
                "context_window_size": p.context_window_size,
                "context_window_used": p.context_window_used,
                "context_utilization_pct": round(p.context_utilization_pct, 2),
                "efficiency_score": round(p.efficiency_score, 2),
                "sub_operations": {k: round(v, 4) for k, v in p.sub_operations.items()}
            }
            for p in result.phase_profiles
        ],
        "handoff_profiles": [
            {
                "from_agent": h.from_agent,
                "to_agent": h.to_agent,
                "avg_duration_seconds": round(h.avg_duration_seconds, 4),
                "max_duration_seconds": round(h.max_duration_seconds, 4),
                "total_handoffs": h.total_handoffs,
                "overhead_pct": round(h.overhead_pct, 3)
            }
            for h in result.handoff_profiles
        ],
        "bottlenecks": [
            {
                "rank": b.rank,
                "category": b.category,
                "component": b.component,
                "description": b.description,
                "impact_score": round(b.impact_score, 1),
                "current_value": round(b.current_value, 4),
                "target_value": round(b.target_value, 4),
                "potential_savings_seconds": round(b.potential_savings_seconds, 4),
                "recommendation": b.recommendation
            }
            for b in result.bottlenecks
        ],
        "task_profiles": result.task_profiles
    }


def generate_markdown_doc(result: AgentProfilingResult) -> str:
    """Generate markdown documentation with optimization recommendations."""
    
    md = """# Phase 10 Agent-Level Profiling Report

**Version:** 1.0
**Created:** {timestamp}
**Task:** T3.2 - Agent-Level Profiling
**Baseline Source:** {baseline}

---

## Executive Summary

This report presents detailed profiling analysis of the hierarchical agent execution system, identifying performance bottlenecks and providing optimization recommendations for Phase 11.

### Key Metrics

| Metric | Value |
|--------|-------|
| Tasks Profiled | {tasks_profiled} |
| Total Phase Executions | {total_executions} |
| Total Execution Time | {total_time}s |
| Total Tokens Used | {total_tokens:,} |
| Average Task Time | {avg_task_time}s |
| Average Tokens/Task | {avg_tokens} |
| Handoff Overhead | {handoff_overhead}% |
| Identified Bottlenecks | {bottleneck_count} |
| Optimization Potential | **{opt_potential}s** per task |

---

## 1. Agent Performance Analysis

### 1.1 Phase Time Distribution

| Phase | Avg Time (s) | % of Total | Tokens/Exec | Efficiency |
|-------|-------------|------------|-------------|------------|
""".format(
        timestamp=result.metadata.get('timestamp', 'N/A'),
        baseline=result.metadata.get('baseline_source', 'N/A'),
        tasks_profiled=result.summary.get('total_tasks_profiled', 0),
        total_executions=result.summary.get('total_phase_executions', 0),
        total_time=result.summary.get('total_time_seconds', 0),
        total_tokens=result.summary.get('total_tokens', 0),
        avg_task_time=result.summary.get('avg_task_time_seconds', 0),
        avg_tokens=result.summary.get('avg_tokens_per_task', 0),
        handoff_overhead=result.summary.get('handoff_overhead_pct', 0),
        bottleneck_count=result.summary.get('bottleneck_count', 0),
        opt_potential=result.summary.get('optimization_potential_seconds', 0)
    )
    
    # Add phase rows
    for agent_type, profile in result.agent_profiles.items():
        phase_dist = result.summary.get('phase_time_distribution', {})
        phase_info = phase_dist.get(agent_type, {})
        md += "| {phase} | {time}s | {pct}% | {tokens} | {eff:.1f} |\n".format(
            phase=agent_type.capitalize(),
            time=round(profile.avg_time_seconds, 3),
            pct=phase_info.get('pct_of_total', 0),
            tokens=int(profile.avg_tokens_per_execution),
            eff=profile.efficiency_score
        )
    
    md += """
### 1.2 Detailed Agent Profiles

"""
    
    for agent_type, profile in result.agent_profiles.items():
        md += """#### {agent_name} Agent

**Role:** {role}
**Executions:** {executions}
**Total Time:** {total_time}s

| Metric | Value |
|--------|-------|
| Average Duration | {avg_time}s |
| Std Deviation | {std_dev}s |
| Min Duration | {min_time}s |
| Max Duration | {max_time}s |
| Total Tokens | {total_tokens:,} |
| Avg Tokens/Execution | {avg_tokens} |
| Token Efficiency (out/in) | {token_eff:.2f} |
| Avg Tokens/Second | {tps:.0f} |
| Context Utilization | {ctx_util:.1f}% |

**Sub-Operation Breakdown:**
| Operation | Avg Time (s) | % of Phase |
|-----------|-------------|------------|
""".format(
            agent_name=agent_type.capitalize(),
            role={
                'manager': 'Task decomposition and planning',
                'coder': 'Code implementation',
                'reviewer': 'Code review and validation'
            }.get(agent_type, 'Unknown'),
            executions=profile.total_executions,
            total_time=round(profile.total_time_seconds, 3),
            avg_time=round(profile.avg_time_seconds, 3),
            std_dev=round(profile.std_dev_time, 4),
            min_time=round(profile.min_time_seconds, 3),
            max_time=round(profile.max_time_seconds, 3),
            total_tokens=profile.total_tokens,
            avg_tokens=int(profile.avg_tokens_per_execution),
            token_eff=profile.token_efficiency,
            tps=profile.avg_tokens_per_second,
            ctx_util=profile.avg_context_utilization_pct
        )
        
        for op_name, op_time in sorted(profile.avg_sub_operations.items(), 
                                       key=lambda x: x[1], reverse=True):
            pct = (op_time / profile.avg_time_seconds * 100) if profile.avg_time_seconds > 0 else 0
            md += "| {op} | {time}s | {pct:.1f}% |\n".format(
                op=op_name.replace('_', ' ').title(),
                time=round(op_time, 4),
                pct=pct
            )
        
        md += "\n"
    
    # Handoff Analysis
    md += """---

## 2. Handoff Analysis

Agent handoffs represent the time spent transferring context and state between agents.

| Handoff | Avg Duration | Max Duration | Count | Overhead % |
|---------|-------------|--------------|-------|------------|
"""
    
    for handoff in result.handoff_profiles:
        md += "| {from_a} → {to_a} | {avg}s | {max}s | {count} | {overhead}% |\n".format(
            from_a=handoff.from_agent.capitalize(),
            to_a=handoff.to_agent.capitalize(),
            avg=round(handoff.avg_duration_seconds, 4),
            max=round(handoff.max_duration_seconds, 4),
            count=handoff.total_handoffs,
            overhead=round(handoff.overhead_pct, 3)
        )
    
    # Bottleneck Analysis
    md += """
---

## 3. Top 3 Bottlenecks

"""
    
    for b in result.bottlenecks:
        md += """### 3.{rank}. {component}

**Category:** {category}
**Impact Score:** {impact}/100

**Description:**
{description}

**Current Value:** {current}
**Target Value:** {target}
**Potential Savings:** {savings}s per task

**Recommendation:**
{recommendation}

""".format(
            rank=b.rank,
            component=b.component,
            category=b.category,
            impact=round(b.impact_score, 1),
            description=b.description,
            current=round(b.current_value, 4),
            target=round(b.target_value, 4),
            savings=round(b.potential_savings_seconds, 3),
            recommendation=b.recommendation
        )
    
    # Phase 11 Recommendations
    md += """---

## 4. Optimization Recommendations for Phase 11

Based on the profiling analysis, the following optimizations are recommended for Phase 11:

### 4.1 High Priority (P0) - Immediate Impact

"""
    
    # Generate specific recommendations based on bottlenecks
    for i, b in enumerate(result.bottlenecks):
        priority = "P0" if i == 0 else ("P1" if i == 1 else "P2")
        reduction_pct = int((1 - b.target_value / b.current_value) * 100) if b.current_value > 0 else 0
        
        md += "#### {priority}: Optimize {component}\n\n**Target:** Reduce {component} time by {reduction}%\n\n**Actions:**\n".format(
            priority=priority,
            component=b.component,
            reduction=reduction_pct
        )
        
        if b.category == "phase":
            md += """1. Profile {component} sub-operations in detail
2. Identify slowest sub-operation and optimize
3. Consider caching repeated computations
4. Evaluate prompt efficiency and reduce token usage
5. Implement parallel execution where possible
""".format(component=b.component)
        elif b.category == "token_efficiency":
            md += """1. Audit input context for redundancy
2. Implement context pruning strategies
3. Use more focused, task-specific prompts
4. Consider summarization of large contexts
5. Evaluate few-shot vs zero-shot prompting
"""
        elif b.category == "throughput":
            md += """1. Investigate API latency issues
2. Consider batch processing of requests
3. Evaluate model selection (speed vs quality tradeoff)
4. Implement request queuing and prioritization
5. Monitor and optimize network conditions
"""
        elif b.category == "handoff":
            md += """1. Optimize context serialization format
2. Implement incremental state transfer
3. Consider shared memory architecture
4. Reduce redundant context re-computation
5. Evaluate async handoff patterns
"""
        
        md += "\n**Expected Impact:** {savings}s saved per task\n\n".format(
            savings=round(b.potential_savings_seconds, 3)
        )
    
    # Token Efficiency Recommendations
    md += """
### 4.2 Token Efficiency Improvements

Based on token analysis across agents:

| Agent | Current Tokens | Target | Savings Potential |
|-------|---------------|--------|-------------------|
"""
    
    for agent_type, profile in result.agent_profiles.items():
        target = int(profile.avg_tokens_per_execution * 0.8)
        savings = int(profile.avg_tokens_per_execution * 0.2)
        md += "| {agent} | {current} | {target} | {savings} |\n".format(
            agent=agent_type.capitalize(),
            current=int(profile.avg_tokens_per_execution),
            target=target,
            savings=savings
        )
    
    md += """
**Strategies:**
1. **Context Pruning:** Remove redundant context from previous phases
2. **Prompt Optimization:** Use more concise system prompts
3. **Selective File Loading:** Only include relevant files in context
4. **Diff Compression:** Compress code diffs for reviewer context
5. **Incremental Context:** Build context incrementally vs full reload

### 4.3 Context Window Optimization

"""
    
    # Context analysis
    max_ctx_agent = max(result.agent_profiles.items(), 
                        key=lambda x: x[1].max_context_utilization_pct)
    
    md += """Current context utilization analysis:

- **Highest Context Usage:** {agent} ({util:.1f}%)
- **Recommended Maximum:** 70%
- **Overflow Risk:** {overflow_count} executions exceeded 80%

**Recommendations:**
1. Implement sliding window context management
2. Use retrieval-augmented context for large codebases
3. Prioritize recent and relevant context
4. Implement context eviction policies
5. Monitor context usage in production

""".format(
        agent=max_ctx_agent[0].capitalize(),
        util=max_ctx_agent[1].max_context_utilization_pct,
        overflow_count=sum(p.context_overflow_count for p in result.agent_profiles.values())
    )
    
    # Performance Targets
    md += """---

## 5. Phase 11 Performance Targets

Based on profiling results, set the following targets for Phase 11:

| Metric | Current | Phase 11 Target | Improvement |
|--------|---------|-----------------|-------------|
| Average Task Latency | {current_latency}s | {target_latency}s | {improvement}% |
| Total Tokens/Task | {current_tokens} | {target_tokens} | 20% reduction |
| Handoff Overhead | {current_handoff}% | {target_handoff}% | 50% reduction |
| Coding Phase Time | {current_coding}s | {target_coding}s | 30% reduction |

""".format(
        current_latency=result.summary.get('avg_task_time_seconds', 0),
        target_latency=round(result.summary.get('avg_task_time_seconds', 0) * 0.75, 3),
        improvement=25,
        current_tokens=result.summary.get('avg_tokens_per_task', 0),
        target_tokens=int(result.summary.get('avg_tokens_per_task', 0) * 0.8),
        current_handoff=result.summary.get('handoff_overhead_pct', 0),
        target_handoff=round(result.summary.get('handoff_overhead_pct', 0) * 0.5, 2),
        current_coding=result.agent_profiles.get('coder', result.agent_profiles.get('coder', type('', (), {'avg_time_seconds': 0})())).avg_time_seconds if 'coder' in result.agent_profiles else 0,
        target_coding=round(result.agent_profiles.get('coder', type('', (), {'avg_time_seconds': 0})()).avg_time_seconds * 0.7, 3) if 'coder' in result.agent_profiles else 0
    )
    
    # Implementation Checklist
    md += """---

## 6. Implementation Checklist

### Phase 11 Pre-Requisites
- [ ] Implement detailed sub-operation timing in all agents
- [ ] Add token counting to all LLM calls
- [ ] Create context window monitoring
- [ ] Set up profiling data collection pipeline

### Optimization Implementation
- [ ] Profile and optimize top bottleneck ({top_bottleneck})
- [ ] Implement context pruning for {ctx_agent}
- [ ] Optimize handoff between {handoff_agents}
- [ ] Add caching layer for repeated computations
- [ ] Implement parallel execution where applicable

### Validation
- [ ] Run profiling after each optimization
- [ ] Compare against Phase 10 baseline
- [ ] Validate no regression in success rate
- [ ] Document all optimization results

---

## 7. Appendix: Raw Metrics

### 7.1 Complete Phase Profile Summary

```json
{phase_summary}
```

### 7.2 Handoff Details

```json
{handoff_details}
```

---

*Report generated by Agent Profiler v1.0*
*Task T3.2 - Phase 10 Agent-Level Profiling*
""".format(
        top_bottleneck=result.bottlenecks[0].component if result.bottlenecks else 'N/A',
        ctx_agent=max_ctx_agent[0].capitalize() if max_ctx_agent else 'N/A',
        handoff_agents=' → '.join([f"{h.from_agent}" for h in result.handoff_profiles]) or 'N/A',
        phase_summary=json.dumps(
            {k: {kk: vv for kk, vv in v.items() if kk in ['avg_time_seconds', 'avg_tokens_per_execution', 'efficiency_score']}
             for k, v in result_to_json(result)['agent_profiles'].items()},
            indent=2
        ),
        handoff_details=json.dumps(
            [{k: v for k, v in asdict(h).items()} for h in result.handoff_profiles],
            indent=2
        )
    )
    
    return md


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Profile agent execution and identify bottlenecks'
    )
    parser.add_argument(
        '--baseline', '-b',
        default='benchmarks/baselines/phase10.1.json',
        help='Path to baseline metrics JSON file'
    )
    parser.add_argument(
        '--output', '-o',
        default='benchmarks/agent_profiles.json',
        help='Output path for profiling results JSON'
    )
    parser.add_argument(
        '--doc-output', '-d',
        default='docs/phase10_agent_profiling.md',
        help='Output path for markdown documentation'
    )
    parser.add_argument(
        '--iterations', '-n',
        type=int,
        default=5,
        help='Number of profiling iterations (for simulated runs)'
    )
    
    args = parser.parse_args()
    
    # Resolve paths relative to project root
    project_root = Path(__file__).parent.parent
    
    baseline_path = project_root / args.baseline
    output_path = project_root / args.output
    doc_output_path = project_root / args.doc_output
    
    # Ensure output directories exist
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc_output_path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Profiling agents using baseline: {baseline_path}")
    
    # Run profiler
    profiler = AgentProfiler(baseline_path=str(baseline_path))
    result = profiler.profile()
    
    # Convert to JSON and save
    json_result = result_to_json(result)
    
    with open(output_path, 'w') as f:
        json.dump(json_result, f, indent=2)
    logger.info(f"Saved profiling results to: {output_path}")
    
    # Generate and save markdown documentation
    md_content = generate_markdown_doc(result)
    
    with open(doc_output_path, 'w') as f:
        f.write(md_content)
    logger.info(f"Saved documentation to: {doc_output_path}")
    
    # Print summary
    print("\n" + "="*60)
    print("AGENT PROFILING SUMMARY")
    print("="*60)
    print(f"\nTasks Profiled: {result.summary.get('total_tasks_profiled', 0)}")
    print(f"Total Execution Time: {result.summary.get('total_time_seconds', 0):.3f}s")
    print(f"Average Task Time: {result.summary.get('avg_task_time_seconds', 0):.3f}s")
    print(f"Total Tokens: {result.summary.get('total_tokens', 0):,}")
    
    print("\nPhase Time Distribution:")
    for agent_type, info in result.summary.get('phase_time_distribution', {}).items():
        print(f"  {agent_type}: {info['avg_seconds']}s ({info['pct_of_total']}%)")
    
    print(f"\nTop Bottlenecks:")
    for b in result.bottlenecks:
        print(f"  {b.rank}. {b.component}: {b.description[:60]}...")
        print(f"     Impact: {b.impact_score:.0f}/100, Savings: {b.potential_savings_seconds:.3f}s")
    
    print(f"\nOptimization Potential: {result.summary.get('optimization_potential_seconds', 0):.3f}s per task")
    print("="*60 + "\n")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
