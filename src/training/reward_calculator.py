"""
Reward Calculator for AutoDev RL Training

This module provides multi-component reward calculation for reinforcement learning
training of code generation models. It computes rewards based on:
- Test pass rate: Primary signal for solution correctness
- Code quality: Static analysis metrics (complexity, maintainability)
- Efficiency: Resource usage (execution time, token count)

Usage:
    from training.reward_calculator import RewardCalculator, RewardConfig
    
    config = RewardConfig(
        test_pass_weight=0.6,
        code_quality_weight=0.25,
        efficiency_weight=0.15
    )
    
    calculator = RewardCalculator(config)
    
    # Compute reward for an execution trace
    reward_components = calculator.compute_reward(trace)
    total_reward = reward_components.total_reward
"""

import ast
import logging
import math
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Union
from enum import Enum

from .data_collector import ExecutionTrace, TraceStatus

logger = logging.getLogger(__name__)


class RewardStrategy(Enum):
    """Strategy for combining reward components."""
    WEIGHTED_SUM = "weighted_sum"  # Simple weighted sum
    GEOMETRIC_MEAN = "geometric_mean"  # Geometric mean (penalizes zeros)
    HARMONIC_MEAN = "harmonic_mean"  # Harmonic mean (strong penalty for zeros)
    PRODUCT = "product"  # Direct product of components


@dataclass
class RewardComponents:
    """
    Individual reward components and their weighted combination.
    
    Attributes:
        test_pass_rate: Reward from test pass rate (0.0 to 1.0)
        code_quality: Reward from code quality metrics (0.0 to 1.0)
        efficiency: Reward from efficiency metrics (0.0 to 1.0)
        success_bonus: Bonus for successful completion (0.0 to bonus value)
        penalty: Penalties for errors/issues (negative value)
        weights: Weights used for each component
        total_reward: Final computed reward
    """
    test_pass_rate: float = 0.0
    code_quality: float = 0.0
    efficiency: float = 0.0
    success_bonus: float = 0.0
    penalty: float = 0.0
    
    # Weights used
    test_pass_weight: float = 0.5
    code_quality_weight: float = 0.3
    efficiency_weight: float = 0.2
    
    # Final reward
    total_reward: float = 0.0
    
    # Metadata
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RewardComponents":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class RewardConfig:
    """
    Configuration for reward calculation.
    
    Attributes:
        test_pass_weight: Weight for test pass rate component
        code_quality_weight: Weight for code quality component
        efficiency_weight: Weight for efficiency component
        strategy: Strategy for combining components
        success_bonus: Bonus for successful task completion
        max_iterations_penalty: Penalty factor for exceeding max iterations
        max_iterations: Maximum expected iterations
        error_penalty: Penalty for execution errors
        timeout_penalty: Penalty for timeout
        normalize_rewards: Whether to normalize rewards to [-1, 1]
        min_efficiency_time: Minimum expected execution time (seconds)
        max_efficiency_time: Maximum expected execution time (seconds)
        min_token_efficiency: Minimum expected tokens per solution
        max_token_efficiency: Maximum expected tokens per solution
    """
    # Component weights (should sum to 1.0)
    test_pass_weight: float = 0.5
    code_quality_weight: float = 0.3
    efficiency_weight: float = 0.2
    
    # Combination strategy
    strategy: RewardStrategy = RewardStrategy.WEIGHTED_SUM
    
    # Bonuses and penalties
    success_bonus: float = 0.1
    max_iterations: int = 20
    iteration_penalty_factor: float = 0.02  # Per iteration over max
    error_penalty: float = 0.3
    timeout_penalty: float = 0.5
    syntax_error_penalty: float = 0.2
    
    # Efficiency thresholds
    min_efficiency_time: float = 10.0  # seconds
    max_efficiency_time: float = 300.0  # seconds
    min_tokens: int = 100
    max_tokens: int = 10000
    
    # Code quality thresholds
    max_complexity: int = 10
    max_line_length: int = 100
    min_comment_ratio: float = 0.05
    
    # Normalization
    normalize_rewards: bool = True
    reward_clip_min: float = -1.0
    reward_clip_max: float = 1.0
    
    def __post_init__(self):
        """Validate configuration."""
        total_weight = self.test_pass_weight + self.code_quality_weight + self.efficiency_weight
        if abs(total_weight - 1.0) > 0.01:
            logger.warning(
                f"Component weights sum to {total_weight}, not 1.0. "
                f"Consider adjusting weights."
            )
        
        if isinstance(self.strategy, str):
            self.strategy = RewardStrategy(self.strategy)


class CodeQualityAnalyzer:
    """
    Analyzes code quality using static analysis.
    
    Provides metrics for:
    - Cyclomatic complexity
    - Line length
    - Comment ratio
    - Syntax validity
    """
    
    def __init__(self, config: Optional[RewardConfig] = None):
        """Initialize with optional config."""
        self.config = config or RewardConfig()
    
    def analyze(self, code: str, language: str = "python") -> Dict[str, Any]:
        """
        Analyze code quality.
        
        Args:
            code: Source code to analyze
            language: Programming language (currently only Python supported)
            
        Returns:
            Dictionary with quality metrics
        """
        if language != "python":
            # For non-Python, use basic heuristics
            return self._analyze_generic(code)
        
        return self._analyze_python(code)
    
    def _analyze_python(self, code: str) -> Dict[str, Any]:
        """Analyze Python code quality."""
        result = {
            "syntax_valid": True,
            "syntax_error": None,
            "complexity": 0,
            "line_count": 0,
            "code_lines": 0,
            "comment_lines": 0,
            "blank_lines": 0,
            "max_line_length": 0,
            "avg_line_length": 0.0,
            "function_count": 0,
            "class_count": 0,
            "import_count": 0,
            "comment_ratio": 0.0,
            "quality_score": 0.0,
        }
        
        if not code or not code.strip():
            result["syntax_valid"] = False
            result["syntax_error"] = "Empty code"
            result["quality_score"] = 0.0
            return result
        
        # Basic line analysis
        lines = code.split("\n")
        result["line_count"] = len(lines)
        
        code_lines = []
        comment_lines = []
        blank_lines = []
        line_lengths = []
        
        for line in lines:
            stripped = line.strip()
            line_lengths.append(len(line))
            
            if not stripped:
                blank_lines.append(line)
            elif stripped.startswith("#"):
                comment_lines.append(line)
            else:
                code_lines.append(line)
                # Count inline comments
                if "#" in stripped and not stripped.startswith("#"):
                    # Has inline comment
                    comment_lines.append(line)
        
        result["code_lines"] = len(code_lines)
        result["comment_lines"] = len(comment_lines)
        result["blank_lines"] = len(blank_lines)
        result["max_line_length"] = max(line_lengths) if line_lengths else 0
        result["avg_line_length"] = sum(line_lengths) / len(line_lengths) if line_lengths else 0
        
        # Calculate comment ratio
        total_significant = result["code_lines"] + result["comment_lines"]
        if total_significant > 0:
            result["comment_ratio"] = result["comment_lines"] / total_significant
        
        # Parse AST for deeper analysis
        try:
            tree = ast.parse(code)
            result["syntax_valid"] = True
            
            # Count structures
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    result["function_count"] += 1
                elif isinstance(node, ast.ClassDef):
                    result["class_count"] += 1
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    result["import_count"] += 1
            
            # Calculate cyclomatic complexity (simplified)
            result["complexity"] = self._calculate_complexity(tree)
            
        except SyntaxError as e:
            result["syntax_valid"] = False
            result["syntax_error"] = str(e)
            result["quality_score"] = 0.0
            return result
        
        # Calculate overall quality score
        result["quality_score"] = self._compute_quality_score(result)
        
        return result
    
    def _analyze_generic(self, code: str) -> Dict[str, Any]:
        """Basic analysis for non-Python code."""
        result = {
            "syntax_valid": True,  # Assume valid
            "syntax_error": None,
            "line_count": 0,
            "code_lines": 0,
            "comment_lines": 0,
            "max_line_length": 0,
            "comment_ratio": 0.0,
            "quality_score": 0.5,  # Default neutral score
        }
        
        if not code or not code.strip():
            result["syntax_valid"] = False
            result["quality_score"] = 0.0
            return result
        
        lines = code.split("\n")
        result["line_count"] = len(lines)
        result["max_line_length"] = max(len(l) for l in lines) if lines else 0
        
        # Simple heuristic for code vs comments
        code_lines = 0
        comment_lines = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(("//", "#", "/*", "*", "--")):
                comment_lines += 1
            elif stripped:
                code_lines += 1
        
        result["code_lines"] = code_lines
        result["comment_lines"] = comment_lines
        
        total = code_lines + comment_lines
        if total > 0:
            result["comment_ratio"] = comment_lines / total
        
        # Basic quality score
        result["quality_score"] = min(1.0, 0.3 + 0.7 * (1 - result["max_line_length"] / 200))
        
        return result
    
    def _calculate_complexity(self, tree: ast.AST) -> int:
        """Calculate cyclomatic complexity (simplified)."""
        complexity = 1  # Base complexity
        
        for node in ast.walk(tree):
            # Decision points increase complexity
            if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                # and/or operators
                complexity += len(node.values) - 1
            elif isinstance(node, (ast.And, ast.Or)):
                complexity += 1
            elif isinstance(node, ast.comprehension):
                complexity += 1
                if node.ifs:
                    complexity += len(node.ifs)
        
        return complexity
    
    def _compute_quality_score(self, metrics: Dict[str, Any]) -> float:
        """Compute overall quality score from metrics."""
        if not metrics.get("syntax_valid", False):
            return 0.0
        
        score = 1.0
        
        # Penalize high complexity
        complexity = metrics.get("complexity", 0)
        max_complexity = self.config.max_complexity
        if complexity > max_complexity:
            complexity_penalty = min(0.3, (complexity - max_complexity) * 0.02)
            score -= complexity_penalty
        
        # Penalize long lines
        max_line = metrics.get("max_line_length", 0)
        if max_line > self.config.max_line_length:
            line_penalty = min(0.2, (max_line - self.config.max_line_length) / 500)
            score -= line_penalty
        
        # Slight bonus for comments (but not required)
        comment_ratio = metrics.get("comment_ratio", 0)
        if comment_ratio >= self.config.min_comment_ratio:
            score += 0.05  # Small bonus
        elif comment_ratio > 0:
            # Partial credit
            score += 0.02
        
        # Penalize very short or very long code
        line_count = metrics.get("code_lines", 0)
        if line_count < 5:
            score -= 0.1  # Too short, likely incomplete
        elif line_count > 500:
            score -= min(0.2, (line_count - 500) / 2500)  # Too long
        
        return max(0.0, min(1.0, score))


class RewardCalculator:
    """
    Calculates multi-component rewards for RL training.
    
    This class computes rewards based on:
    1. Test pass rate - Primary correctness signal
    2. Code quality - Static analysis metrics
    3. Efficiency - Resource usage metrics
    
    The components are combined using configurable weights and strategy.
    
    Example:
        config = RewardConfig(
            test_pass_weight=0.6,
            code_quality_weight=0.25,
            efficiency_weight=0.15
        )
        calculator = RewardCalculator(config)
        
        # Compute reward
        components = calculator.compute_reward(trace)
        print(f"Total reward: {components.total_reward}")
        print(f"Test pass rate: {components.test_pass_rate}")
    """
    
    def __init__(self, config: Optional[RewardConfig] = None):
        """
        Initialize the reward calculator.
        
        Args:
            config: Reward calculation configuration
        """
        self.config = config or RewardConfig()
        self.quality_analyzer = CodeQualityAnalyzer(self.config)
        
        logger.info(
            f"RewardCalculator initialized with weights: "
            f"test={self.config.test_pass_weight}, "
            f"quality={self.config.code_quality_weight}, "
            f"efficiency={self.config.efficiency_weight}"
        )
    
    def compute_reward(
        self,
        trace: ExecutionTrace,
        additional_metrics: Optional[Dict[str, Any]] = None
    ) -> RewardComponents:
        """
        Compute multi-component reward for an execution trace.
        
        Args:
            trace: Execution trace to compute reward for
            additional_metrics: Optional additional metrics to consider
            
        Returns:
            RewardComponents with individual scores and total reward
        """
        components = RewardComponents(
            test_pass_weight=self.config.test_pass_weight,
            code_quality_weight=self.config.code_quality_weight,
            efficiency_weight=self.config.efficiency_weight,
        )
        
        # Compute individual components
        components.test_pass_rate = self._compute_test_pass_rate(trace)
        components.code_quality = self._compute_code_quality(trace)
        components.efficiency = self._compute_efficiency(trace)
        
        # Apply bonuses and penalties
        components.success_bonus = self._compute_success_bonus(trace)
        components.penalty = self._compute_penalties(trace)
        
        # Combine components
        components.total_reward = self._combine_components(components)
        
        # Apply final adjustments
        components.total_reward += components.success_bonus
        components.total_reward -= components.penalty
        
        # Normalize and clip
        if self.config.normalize_rewards:
            components.total_reward = self._normalize_reward(components.total_reward)
        
        # Store details
        components.details = {
            "strategy": self.config.strategy.value,
            "trace_id": trace.trace_id,
            "task_id": trace.task_id,
            "status": trace.status.value,
            "tests_passed_count": len(trace.tests_passed),
            "tests_failed_count": len(trace.tests_failed),
            "iterations": trace.iterations,
            "execution_time": trace.execution_time_seconds,
        }
        
        # Update trace reward
        trace.reward = components.total_reward
        
        return components
    
    def compute_batch_rewards(
        self,
        traces: List[ExecutionTrace]
    ) -> List[RewardComponents]:
        """
        Compute rewards for multiple traces.
        
        Args:
            traces: List of execution traces
            
        Returns:
            List of RewardComponents for each trace
        """
        return [self.compute_reward(trace) for trace in traces]
    
    def _compute_test_pass_rate(self, trace: ExecutionTrace) -> float:
        """Compute test pass rate reward component."""
        total_tests = len(trace.tests_passed) + len(trace.tests_failed)
        
        if total_tests == 0:
            # No tests found
            if trace.status == TraceStatus.SUCCESS:
                # Successful but no tests - give partial credit
                return 0.7
            elif trace.status == TraceStatus.PARTIAL:
                return 0.5
            else:
                return 0.0
        
        pass_rate = len(trace.tests_passed) / total_tests
        
        # Scale to reward range
        # Pass rate of 1.0 -> reward of 1.0
        # Pass rate of 0.0 -> reward of 0.0
        return pass_rate
    
    def _compute_code_quality(self, trace: ExecutionTrace) -> float:
        """Compute code quality reward component."""
        if not trace.code_changes:
            # No code changes
            if trace.status == TraceStatus.SUCCESS:
                # Success without code changes might be valid (e.g., config change)
                return 0.8
            return 0.3  # Low score for no code
        
        # Analyze each code change
        quality_scores = []
        syntax_errors = 0
        
        for change in trace.code_changes:
            if change.new_content:
                metrics = self.quality_analyzer.analyze(
                    change.new_content,
                    change.language
                )
                quality_scores.append(metrics.get("quality_score", 0.5))
                
                if not metrics.get("syntax_valid", True):
                    syntax_errors += 1
        
        if not quality_scores:
            return 0.3
        
        # Average quality score
        avg_quality = sum(quality_scores) / len(quality_scores)
        
        # Penalize syntax errors
        if syntax_errors > 0:
            syntax_penalty = min(0.3, syntax_errors * 0.1)
            avg_quality -= syntax_penalty
        
        return max(0.0, min(1.0, avg_quality))
    
    def _compute_efficiency(self, trace: ExecutionTrace) -> float:
        """Compute efficiency reward component."""
        score = 1.0
        
        # Time efficiency
        time = trace.execution_time_seconds
        if time > 0:
            if time <= self.config.min_efficiency_time:
                time_score = 1.0
            elif time >= self.config.max_efficiency_time:
                time_score = 0.0
            else:
                # Linear interpolation
                range_time = self.config.max_efficiency_time - self.config.min_efficiency_time
                time_score = 1.0 - (time - self.config.min_efficiency_time) / range_time
        else:
            time_score = 0.5  # Unknown time
        
        # Iteration efficiency
        iterations = trace.iterations
        if iterations <= 0:
            iter_score = 0.5
        elif iterations <= self.config.max_iterations:
            iter_score = 1.0 - (iterations / self.config.max_iterations) * 0.3
        else:
            # Penalty for exceeding max iterations
            excess = iterations - self.config.max_iterations
            iter_score = max(0.0, 0.7 - excess * 0.05)
        
        # Token efficiency
        tokens = trace.total_tokens.get("total", 0)
        if tokens > 0:
            if tokens <= self.config.min_tokens:
                token_score = 0.8  # Very efficient but might be incomplete
            elif tokens >= self.config.max_tokens:
                token_score = 0.2  # Very inefficient
            else:
                range_tokens = self.config.max_tokens - self.config.min_tokens
                token_score = 1.0 - (tokens - self.config.min_tokens) / range_tokens * 0.6
        else:
            token_score = 0.5  # Unknown
        
        # Combine efficiency scores
        # Weight: time 40%, iterations 40%, tokens 20%
        score = 0.4 * time_score + 0.4 * iter_score + 0.2 * token_score
        
        return max(0.0, min(1.0, score))
    
    def _compute_success_bonus(self, trace: ExecutionTrace) -> float:
        """Compute bonus for successful completion."""
        if trace.status == TraceStatus.SUCCESS:
            return self.config.success_bonus
        elif trace.status == TraceStatus.PARTIAL:
            return self.config.success_bonus * 0.3
        return 0.0
    
    def _compute_penalties(self, trace: ExecutionTrace) -> float:
        """Compute penalties for errors and issues."""
        penalty = 0.0
        
        # Error penalty
        if trace.status == TraceStatus.ERROR:
            penalty += self.config.error_penalty
        elif trace.status == TraceStatus.TIMEOUT:
            penalty += self.config.timeout_penalty
        
        # Iteration penalty
        if trace.iterations > self.config.max_iterations:
            excess = trace.iterations - self.config.max_iterations
            penalty += excess * self.config.iteration_penalty_factor
        
        # Syntax error penalty (from code quality analysis)
        for change in trace.code_changes:
            if change.new_content:
                metrics = self.quality_analyzer.analyze(
                    change.new_content,
                    change.language
                )
                if not metrics.get("syntax_valid", True):
                    penalty += self.config.syntax_error_penalty
        
        return penalty
    
    def _combine_components(self, components: RewardComponents) -> float:
        """Combine reward components using configured strategy."""
        w_test = self.config.test_pass_weight
        w_quality = self.config.code_quality_weight
        w_efficiency = self.config.efficiency_weight
        
        test = components.test_pass_rate
        quality = components.code_quality
        efficiency = components.efficiency
        
        if self.config.strategy == RewardStrategy.WEIGHTED_SUM:
            return w_test * test + w_quality * quality + w_efficiency * efficiency
        
        elif self.config.strategy == RewardStrategy.GEOMETRIC_MEAN:
            # Weighted geometric mean
            # Avoid log(0) by adding small epsilon
            eps = 1e-10
            weighted_product = (
                (test + eps) ** w_test *
                (quality + eps) ** w_quality *
                (efficiency + eps) ** w_efficiency
            )
            return weighted_product
        
        elif self.config.strategy == RewardStrategy.HARMONIC_MEAN:
            # Weighted harmonic mean
            # Avoid division by zero
            if test <= 0 or quality <= 0 or efficiency <= 0:
                return 0.0
            denominator = w_test / test + w_quality / quality + w_efficiency / efficiency
            if denominator <= 0:
                return 0.0
            return 1.0 / denominator
        
        elif self.config.strategy == RewardStrategy.PRODUCT:
            # Simple product (rewards must be well-calibrated)
            return test * quality * efficiency
        
        else:
            # Default to weighted sum
            return w_test * test + w_quality * quality + w_efficiency * efficiency
    
    def _normalize_reward(self, reward: float) -> float:
        """Normalize reward to configured range."""
        return max(
            self.config.reward_clip_min,
            min(self.config.reward_clip_max, reward)
        )
    
    def get_reward_explanation(self, components: RewardComponents) -> str:
        """
        Get a human-readable explanation of the reward.
        
        Args:
            components: RewardComponents to explain
            
        Returns:
            Human-readable explanation string
        """
        lines = [
            f"Total Reward: {components.total_reward:.4f}",
            "",
            "Components:",
            f"  Test Pass Rate: {components.test_pass_rate:.4f} (weight: {components.test_pass_weight})",
            f"  Code Quality:   {components.code_quality:.4f} (weight: {components.code_quality_weight})",
            f"  Efficiency:     {components.efficiency:.4f} (weight: {components.efficiency_weight})",
            "",
            "Adjustments:",
            f"  Success Bonus: +{components.success_bonus:.4f}",
            f"  Penalties:     -{components.penalty:.4f}",
        ]
        
        if components.details:
            lines.append("")
            lines.append("Details:")
            for key, value in components.details.items():
                lines.append(f"  {key}: {value}")
        
        return "\n".join(lines)


# Convenience functions

def create_calculator(
    test_pass_weight: float = 0.5,
    code_quality_weight: float = 0.3,
    efficiency_weight: float = 0.2,
    strategy: str = "weighted_sum",
    **kwargs
) -> RewardCalculator:
    """
    Create a RewardCalculator with simplified configuration.
    
    Args:
        test_pass_weight: Weight for test pass rate
        code_quality_weight: Weight for code quality
        efficiency_weight: Weight for efficiency
        strategy: Combination strategy ("weighted_sum", "geometric_mean", etc.)
        **kwargs: Additional RewardConfig parameters
        
    Returns:
        Configured RewardCalculator
    """
    config = RewardConfig(
        test_pass_weight=test_pass_weight,
        code_quality_weight=code_quality_weight,
        efficiency_weight=efficiency_weight,
        strategy=RewardStrategy(strategy),
        **kwargs
    )
    return RewardCalculator(config)


def compute_reward(
    trace: ExecutionTrace,
    config: Optional[RewardConfig] = None
) -> float:
    """
    Convenience function to compute reward for a trace.
    
    Args:
        trace: Execution trace
        config: Optional reward configuration
        
    Returns:
        Total reward value
    """
    calculator = RewardCalculator(config)
    components = calculator.compute_reward(trace)
    return components.total_reward
