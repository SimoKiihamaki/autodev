"""
Tests for Reward Calculator

Run with: pytest src/training/test_reward_calculator.py -v
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import Mock, patch

from training.reward_calculator import (
    RewardCalculator,
    RewardConfig,
    RewardComponents,
    RewardStrategy,
    CodeQualityAnalyzer,
    create_calculator,
    compute_reward,
)
from training.data_collector import (
    ExecutionTrace,
    TraceStep,
    CodeChange,
    TraceStatus,
)


class TestRewardConfig:
    """Tests for RewardConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = RewardConfig()
        
        assert config.test_pass_weight == 0.5
        assert config.code_quality_weight == 0.3
        assert config.efficiency_weight == 0.2
        assert config.strategy == RewardStrategy.WEIGHTED_SUM
        assert config.success_bonus == 0.1
        assert config.max_iterations == 20
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = RewardConfig(
            test_pass_weight=0.6,
            code_quality_weight=0.25,
            efficiency_weight=0.15,
            success_bonus=0.2,
            max_iterations=10
        )
        
        assert config.test_pass_weight == 0.6
        assert config.code_quality_weight == 0.25
        assert config.efficiency_weight == 0.15
        assert config.success_bonus == 0.2
        assert config.max_iterations == 10
    
    def test_strategy_from_string(self):
        """Test creating strategy from string."""
        config = RewardConfig(strategy="geometric_mean")
        assert config.strategy == RewardStrategy.GEOMETRIC_MEAN
    
    def test_weight_warning(self, caplog):
        """Test warning when weights don't sum to 1.0."""
        RewardConfig(
            test_pass_weight=0.5,
            code_quality_weight=0.4,
            efficiency_weight=0.2  # Total: 1.1
        )
        assert "weights sum to 1.1" in caplog.text


class TestRewardComponents:
    """Tests for RewardComponents dataclass."""
    
    def test_create_components(self):
        """Test creating reward components."""
        components = RewardComponents(
            test_pass_rate=0.8,
            code_quality=0.7,
            efficiency=0.9,
            total_reward=0.75
        )
        
        assert components.test_pass_rate == 0.8
        assert components.code_quality == 0.7
        assert components.efficiency == 0.9
        assert components.total_reward == 0.75
    
    def test_serialization(self):
        """Test serializing and deserializing components."""
        components = RewardComponents(
            test_pass_rate=0.8,
            code_quality=0.7,
            efficiency=0.9,
            success_bonus=0.1,
            penalty=0.05,
            total_reward=0.8
        )
        
        data = components.to_dict()
        assert data["test_pass_rate"] == 0.8
        
        restored = RewardComponents.from_dict(data)
        assert restored.test_pass_rate == components.test_pass_rate
        assert restored.total_reward == components.total_reward


class TestCodeQualityAnalyzer:
    """Tests for CodeQualityAnalyzer."""
    
    def test_analyze_simple_code(self):
        """Test analyzing simple Python code."""
        analyzer = CodeQualityAnalyzer()
        code = '''
def hello():
    """Say hello."""
    print("Hello, World!")
    return True
'''
        result = analyzer.analyze(code)
        
        assert result["syntax_valid"] is True
        assert result["function_count"] == 1
        assert result["quality_score"] > 0
    
    def test_analyze_invalid_syntax(self):
        """Test analyzing code with syntax errors."""
        analyzer = CodeQualityAnalyzer()
        code = "def broken(\n"  # Invalid syntax
        
        result = analyzer.analyze(code)
        
        assert result["syntax_valid"] is False
        assert result["syntax_error"] is not None
        assert result["quality_score"] == 0.0
    
    def test_analyze_empty_code(self):
        """Test analyzing empty code."""
        analyzer = CodeQualityAnalyzer()
        
        result = analyzer.analyze("")
        assert result["syntax_valid"] is False
        assert result["quality_score"] == 0.0
        
        result = analyzer.analyze("   \n  \n")
        assert result["syntax_valid"] is False
    
    def test_analyze_complexity(self):
        """Test complexity calculation."""
        analyzer = CodeQualityAnalyzer()
        code = '''
def complex_function(x):
    if x > 0:
        if x > 10:
            return "big"
        else:
            return "small"
    elif x < 0:
        return "negative"
    else:
        return "zero"
'''
        result = analyzer.analyze(code)
        
        assert result["syntax_valid"] is True
        assert result["complexity"] > 1  # More than base complexity
    
    def test_analyze_comments(self):
        """Test comment ratio calculation."""
        analyzer = CodeQualityAnalyzer()
        code = '''
# This is a comment
def func():
    """Docstring"""
    # Another comment
    x = 1  # inline comment
    return x
'''
        result = analyzer.analyze(code)
        
        assert result["comment_ratio"] > 0
    
    def test_analyze_line_metrics(self):
        """Test line-related metrics."""
        analyzer = CodeQualityAnalyzer()
        code = "x = 1\n" + "y = 2\n" + "z = 3"  # 3 lines, last without trailing newline
        
        result = analyzer.analyze(code)
        
        assert result["line_count"] == 3
        assert result["max_line_length"] == 5
    
    def test_analyze_generic_code(self):
        """Test analyzing non-Python code."""
        analyzer = CodeQualityAnalyzer()
        code = '''
// JavaScript code
function hello() {
    console.log("Hello");
    return true;
}
'''
        result = analyzer.analyze(code, language="javascript")
        
        # Should use generic analyzer
        assert "quality_score" in result


class TestRewardCalculator:
    """Tests for RewardCalculator."""
    
    @pytest.fixture
    def calculator(self):
        """Create a default calculator."""
        return RewardCalculator()
    
    @pytest.fixture
    def custom_calculator(self):
        """Create a calculator with custom config."""
        config = RewardConfig(
            test_pass_weight=0.6,
            code_quality_weight=0.25,
            efficiency_weight=0.15,
            success_bonus=0.2
        )
        return RewardCalculator(config)
    
    @pytest.fixture
    def successful_trace(self):
        """Create a successful execution trace."""
        trace = ExecutionTrace(
            trace_id="",
            task_id="test-task-123",
            timestamp="2026-03-23T12:00:00",
            problem_statement="Fix the bug"
        )
        trace.status = TraceStatus.SUCCESS
        trace.tests_passed = ["test_one", "test_two", "test_three"]
        trace.tests_failed = []
        trace.execution_time_seconds = 30.0
        trace.iterations = 5
        
        # Add code change
        change = CodeChange(
            file_path="test.py",
            change_type="modify",
            new_content="def fixed():\n    return True\n"
        )
        trace.code_changes.append(change)
        
        return trace
    
    @pytest.fixture
    def failed_trace(self):
        """Create a failed execution trace."""
        trace = ExecutionTrace(
            trace_id="",
            task_id="test-task-456",
            timestamp="2026-03-23T12:00:00",
            problem_statement="Fix the bug"
        )
        trace.status = TraceStatus.FAILED
        trace.tests_passed = ["test_one"]
        trace.tests_failed = ["test_two", "test_three"]
        trace.execution_time_seconds = 120.0
        trace.iterations = 15
        
        return trace
    
    def test_create_calculator(self, calculator):
        """Test calculator initialization."""
        assert calculator.config is not None
        assert calculator.quality_analyzer is not None
    
    def test_compute_reward_success(self, calculator, successful_trace):
        """Test computing reward for successful trace."""
        components = calculator.compute_reward(successful_trace)
        
        assert components.test_pass_rate == 1.0  # All tests passed
        assert components.code_quality > 0
        assert components.efficiency > 0
        assert components.success_bonus == calculator.config.success_bonus
        assert components.total_reward > 0
    
    def test_compute_reward_failure(self, calculator, failed_trace):
        """Test computing reward for failed trace."""
        components = calculator.compute_reward(failed_trace)
        
        # Test pass rate should be 1/3
        assert components.test_pass_rate == pytest.approx(1/3, rel=0.01)
        # No success bonus for failure
        assert components.success_bonus == 0.0
        # Total reward should be lower than success
        assert components.total_reward < 0.7
    
    def test_compute_reward_updates_trace(self, calculator, successful_trace):
        """Test that compute_reward updates trace.reward."""
        components = calculator.compute_reward(successful_trace)
        
        assert successful_trace.reward == components.total_reward
    
    def test_test_pass_rate_no_tests(self, calculator):
        """Test pass rate when no tests are present."""
        trace = ExecutionTrace(
            trace_id="",
            task_id="test-task",
            timestamp="",
            problem_statement="Test"
        )
        trace.status = TraceStatus.SUCCESS
        trace.tests_passed = []
        trace.tests_failed = []
        
        rate = calculator._compute_test_pass_rate(trace)
        # Success with no tests should give partial credit
        assert 0 < rate < 1
    
    def test_code_quality_no_changes(self, calculator):
        """Test code quality with no code changes."""
        trace = ExecutionTrace(
            trace_id="",
            task_id="test-task",
            timestamp="",
            problem_statement="Test"
        )
        trace.code_changes = []
        trace.status = TraceStatus.FAILED
        
        quality = calculator._compute_code_quality(trace)
        assert quality < 0.5  # Should be low for no code
    
    def test_code_quality_with_syntax_error(self, calculator):
        """Test code quality with syntax error."""
        trace = ExecutionTrace(
            trace_id="",
            task_id="test-task",
            timestamp="",
            problem_statement="Test"
        )
        
        # Add code with syntax error
        change = CodeChange(
            file_path="test.py",
            change_type="create",
            new_content="def broken(\n"  # Invalid syntax
        )
        trace.code_changes.append(change)
        
        quality = calculator._compute_code_quality(trace)
        assert quality < 0.5  # Should be penalized
    
    def test_efficiency_fast_execution(self, calculator):
        """Test efficiency with fast execution."""
        trace = ExecutionTrace(
            trace_id="",
            task_id="test-task",
            timestamp="",
            problem_statement="Test"
        )
        trace.execution_time_seconds = 5.0  # Very fast
        trace.iterations = 3
        trace.total_tokens = {"total": 500}
        
        efficiency = calculator._compute_efficiency(trace)
        assert efficiency > 0.8  # Should be high for fast execution
    
    def test_efficiency_slow_execution(self, calculator):
        """Test efficiency with slow execution."""
        trace = ExecutionTrace(
            trace_id="",
            task_id="test-task",
            timestamp="",
            problem_statement="Test"
        )
        trace.execution_time_seconds = 400.0  # Very slow
        trace.iterations = 25  # Over max
        trace.total_tokens = {"total": 15000}  # Over max
        
        efficiency = calculator._compute_efficiency(trace)
        assert efficiency < 0.5  # Should be low
    
    def test_success_bonus(self, calculator):
        """Test success bonus calculation."""
        trace = ExecutionTrace(
            trace_id="",
            task_id="test-task",
            timestamp="",
            problem_statement="Test"
        )
        
        # Full success
        trace.status = TraceStatus.SUCCESS
        bonus = calculator._compute_success_bonus(trace)
        assert bonus == calculator.config.success_bonus
        
        # Partial success
        trace.status = TraceStatus.PARTIAL
        bonus = calculator._compute_success_bonus(trace)
        assert 0 < bonus < calculator.config.success_bonus
        
        # Failure
        trace.status = TraceStatus.FAILED
        bonus = calculator._compute_success_bonus(trace)
        assert bonus == 0.0
    
    def test_penalties(self, calculator):
        """Test penalty calculation."""
        trace = ExecutionTrace(
            trace_id="",
            task_id="test-task",
            timestamp="",
            problem_statement="Test"
        )
        
        # No penalties
        trace.status = TraceStatus.SUCCESS
        trace.iterations = 5
        penalty = calculator._compute_penalties(trace)
        assert penalty == 0.0
        
        # Error penalty
        trace.status = TraceStatus.ERROR
        penalty = calculator._compute_penalties(trace)
        assert penalty > 0
        
        # Timeout penalty
        trace.status = TraceStatus.TIMEOUT
        penalty = calculator._compute_penalties(trace)
        assert penalty > 0
        
        # Iteration penalty
        trace.status = TraceStatus.FAILED
        trace.iterations = 30  # Over max
        penalty = calculator._compute_penalties(trace)
        assert penalty > 0
    
    def test_combine_components_weighted_sum(self, calculator):
        """Test weighted sum combination."""
        calculator.config.strategy = RewardStrategy.WEIGHTED_SUM
        
        components = RewardComponents(
            test_pass_rate=1.0,
            code_quality=1.0,
            efficiency=1.0
        )
        
        result = calculator._combine_components(components)
        assert result == 1.0  # All 1.0 should give 1.0
    
    def test_combine_components_geometric_mean(self, calculator):
        """Test geometric mean combination."""
        calculator.config.strategy = RewardStrategy.GEOMETRIC_MEAN
        
        components = RewardComponents(
            test_pass_rate=1.0,
            code_quality=1.0,
            efficiency=1.0
        )
        
        result = calculator._combine_components(components)
        assert result == pytest.approx(1.0, rel=0.01)
        
        # Zero in one component should reduce result
        components.test_pass_rate = 0.0
        result = calculator._combine_components(components)
        assert result < 1.0
    
    def test_combine_components_harmonic_mean(self, calculator):
        """Test harmonic mean combination."""
        calculator.config.strategy = RewardStrategy.HARMONIC_MEAN
        
        components = RewardComponents(
            test_pass_rate=1.0,
            code_quality=1.0,
            efficiency=1.0
        )
        
        result = calculator._combine_components(components)
        assert result == pytest.approx(1.0, rel=0.01)
    
    def test_combine_components_harmonic_mean_zero(self, calculator):
        """Test harmonic mean with zero component."""
        calculator.config.strategy = RewardStrategy.HARMONIC_MEAN
        
        components = RewardComponents(
            test_pass_rate=0.0,  # Zero
            code_quality=1.0,
            efficiency=1.0
        )
        
        result = calculator._combine_components(components)
        assert result == 0.0  # Should be zero with harmonic mean
    
    def test_normalize_reward(self, calculator):
        """Test reward normalization."""
        # Within range
        assert calculator._normalize_reward(0.5) == 0.5
        
        # Above max
        assert calculator._normalize_reward(2.0) == calculator.config.reward_clip_max
        
        # Below min
        assert calculator._normalize_reward(-2.0) == calculator.config.reward_clip_min
    
    def test_batch_rewards(self, calculator):
        """Test computing rewards for multiple traces."""
        traces = []
        
        for i in range(3):
            trace = ExecutionTrace(
                trace_id=f"trace_{i}",
                task_id=f"task_{i}",
                timestamp="2026-03-23T12:00:00",
                problem_statement=f"Problem {i}"
            )
            trace.tests_passed = [f"test_{j}" for j in range(i + 1)]
            trace.tests_failed = [f"test_{j}" for j in range(i + 1, 3)]
            trace.status = TraceStatus.SUCCESS if i == 2 else TraceStatus.FAILED
            traces.append(trace)
        
        components_list = calculator.compute_batch_rewards(traces)
        
        assert len(components_list) == 3
        # Last trace should have highest reward (all tests passed)
        assert components_list[2].total_reward > components_list[0].total_reward
    
    def test_get_reward_explanation(self, calculator, successful_trace):
        """Test reward explanation generation."""
        components = calculator.compute_reward(successful_trace)
        explanation = calculator.get_reward_explanation(components)
        
        assert "Total Reward" in explanation
        assert "Test Pass Rate" in explanation
        assert "Code Quality" in explanation
        assert "Efficiency" in explanation


class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    def test_create_calculator_func(self):
        """Test create_calculator function."""
        calculator = create_calculator(
            test_pass_weight=0.6,
            code_quality_weight=0.3,
            efficiency_weight=0.1,
            strategy="geometric_mean"
        )
        
        assert calculator.config.test_pass_weight == 0.6
        assert calculator.config.code_quality_weight == 0.3
        assert calculator.config.efficiency_weight == 0.1
        assert calculator.config.strategy == RewardStrategy.GEOMETRIC_MEAN
    
    def test_compute_reward_func(self):
        """Test compute_reward convenience function."""
        trace = ExecutionTrace(
            trace_id="",
            task_id="test-task",
            timestamp="",
            problem_statement="Test"
        )
        trace.status = TraceStatus.SUCCESS
        trace.tests_passed = ["test_one"]
        trace.tests_failed = []
        
        reward = compute_reward(trace)
        
        assert isinstance(reward, float)
        assert reward > 0
    
    def test_compute_reward_with_config(self):
        """Test compute_reward with custom config."""
        config = RewardConfig(
            test_pass_weight=0.8,
            success_bonus=0.3
        )
        
        trace = ExecutionTrace(
            trace_id="",
            task_id="test-task",
            timestamp="",
            problem_statement="Test"
        )
        trace.status = TraceStatus.SUCCESS
        trace.tests_passed = ["test_one"]
        
        reward = compute_reward(trace, config)
        assert reward > 0


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_trace_with_nothing(self):
        """Test trace with minimal data."""
        calculator = RewardCalculator()
        trace = ExecutionTrace(
            trace_id="",
            task_id="test",
            timestamp="",
            problem_statement=""
        )
        
        components = calculator.compute_reward(trace)
        
        # Should not crash and return valid components
        assert isinstance(components, RewardComponents)
        assert components.total_reward >= -1.0
        assert components.total_reward <= 1.0
    
    def test_very_long_execution_time(self):
        """Test with very long execution time."""
        calculator = RewardCalculator()
        trace = ExecutionTrace(
            trace_id="",
            task_id="test",
            timestamp="",
            problem_statement="Test"
        )
        trace.execution_time_seconds = 10000.0  # Very long
        
        efficiency = calculator._compute_efficiency(trace)
        assert efficiency >= 0.0
    
    def test_many_iterations(self):
        """Test with many iterations."""
        calculator = RewardCalculator()
        trace = ExecutionTrace(
            trace_id="",
            task_id="test",
            timestamp="",
            problem_statement="Test"
        )
        trace.iterations = 100
        
        penalty = calculator._compute_penalties(trace)
        assert penalty > 0
    
    def test_many_code_changes(self):
        """Test with many code changes."""
        calculator = RewardCalculator()
        trace = ExecutionTrace(
            trace_id="",
            task_id="test",
            timestamp="",
            problem_statement="Test"
        )
        
        # Add many code changes
        for i in range(10):
            change = CodeChange(
                file_path=f"file_{i}.py",
                change_type="modify",
                new_content=f"# File {i}\nx = {i}\n"
            )
            trace.code_changes.append(change)
        
        quality = calculator._compute_code_quality(trace)
        assert 0 <= quality <= 1.0
    
    def test_mixed_quality_code(self):
        """Test with mix of good and bad code."""
        calculator = RewardCalculator()
        trace = ExecutionTrace(
            trace_id="",
            task_id="test",
            timestamp="",
            problem_statement="Test"
        )
        
        # Good code
        trace.code_changes.append(CodeChange(
            file_path="good.py",
            change_type="create",
            new_content="def good():\n    return True\n"
        ))
        
        # Bad code (syntax error)
        trace.code_changes.append(CodeChange(
            file_path="bad.py",
            change_type="create",
            new_content="def broken(\n"
        ))
        
        quality = calculator._compute_code_quality(trace)
        # Should average between them
        assert 0 < quality < 1.0


class TestDifferentStrategies:
    """Tests for different combination strategies."""
    
    @pytest.fixture
    def sample_trace(self):
        """Create a sample trace."""
        trace = ExecutionTrace(
            trace_id="",
            task_id="test",
            timestamp="",
            problem_statement="Test"
        )
        trace.status = TraceStatus.SUCCESS
        trace.tests_passed = ["test_one", "test_two"]
        trace.tests_failed = ["test_three"]
        trace.iterations = 5
        trace.execution_time_seconds = 30.0
        
        trace.code_changes.append(CodeChange(
            file_path="test.py",
            change_type="modify",
            new_content="x = 1\n"
        ))
        
        return trace
    
    def test_weighted_sum_strategy(self, sample_trace):
        """Test weighted sum strategy."""
        config = RewardConfig(strategy=RewardStrategy.WEIGHTED_SUM)
        calculator = RewardCalculator(config)
        
        components = calculator.compute_reward(sample_trace)
        
        expected = (
            config.test_pass_weight * components.test_pass_rate +
            config.code_quality_weight * components.code_quality +
            config.efficiency_weight * components.efficiency
        )
        
        assert components.total_reward >= expected - 0.1  # Allow for bonuses
    
    def test_geometric_mean_strategy(self, sample_trace):
        """Test geometric mean strategy."""
        config = RewardConfig(strategy=RewardStrategy.GEOMETRIC_MEAN)
        calculator = RewardCalculator(config)
        
        components = calculator.compute_reward(sample_trace)
        
        assert 0 <= components.total_reward <= 1.0
    
    def test_harmonic_mean_strategy(self, sample_trace):
        """Test harmonic mean strategy."""
        config = RewardConfig(strategy=RewardStrategy.HARMONIC_MEAN)
        calculator = RewardCalculator(config)
        
        components = calculator.compute_reward(sample_trace)
        
        assert 0 <= components.total_reward <= 1.0
    
    def test_product_strategy(self, sample_trace):
        """Test product strategy."""
        config = RewardConfig(strategy=RewardStrategy.PRODUCT)
        calculator = RewardCalculator(config)
        
        components = calculator.compute_reward(sample_trace)
        
        expected = (
            components.test_pass_rate *
            components.code_quality *
            components.efficiency
        )
        
        # Product gives lower values
        assert components.total_reward >= expected - 0.1


class TestIntegration:
    """Integration tests for reward calculator."""
    
    def test_full_pipeline(self):
        """Test full reward calculation pipeline."""
        # Create trace with realistic data
        trace = ExecutionTrace(
            trace_id="",
            task_id="django__django-12345",
            timestamp="2026-03-23T10:00:00Z",
            problem_statement="Fix bug in ORM query handling"
        )
        
        trace.status = TraceStatus.SUCCESS
        trace.tests_passed = [
            "test_basic_query",
            "test_complex_query",
            "test_edge_case"
        ]
        trace.tests_failed = []
        trace.execution_time_seconds = 45.5
        trace.iterations = 8
        
        trace.code_changes.append(CodeChange(
            file_path="django/db/models/query.py",
            change_type="modify",
            new_content='''
def execute_query(self, query):
    """Execute the given query with proper error handling."""
    if not query:
        return []
    
    try:
        result = self._execute(query)
        return self._process(result)
    except QueryError as e:
        logger.warning(f"Query failed: {e}")
        return []
''',
            language="python"
        ))
        
        trace.total_tokens = {"input": 500, "output": 300, "total": 800}
        
        # Calculate reward
        config = RewardConfig(
            test_pass_weight=0.5,
            code_quality_weight=0.3,
            efficiency_weight=0.2,
            success_bonus=0.1
        )
        
        calculator = RewardCalculator(config)
        components = calculator.compute_reward(trace)
        
        # Verify results
        assert components.test_pass_rate == 1.0  # All tests passed
        assert components.code_quality > 0.5  # Good code
        assert components.efficiency > 0.5  # Reasonable efficiency
        assert components.success_bonus == 0.1  # Success bonus applied
        assert components.total_reward > 0.7  # High overall reward
        
        # Verify trace was updated
        assert trace.reward == components.total_reward
    
    def test_partial_success_scenario(self):
        """Test partial success scenario."""
        trace = ExecutionTrace(
            trace_id="",
            task_id="test-partial",
            timestamp="",
            problem_statement="Partial fix"
        )
        
        trace.status = TraceStatus.PARTIAL
        trace.tests_passed = ["test_one"]
        trace.tests_failed = ["test_two", "test_three"]
        trace.execution_time_seconds = 120.0
        trace.iterations = 18  # Close to max
        
        calculator = RewardCalculator()
        components = calculator.compute_reward(trace)
        
        # Should have lower but positive reward
        assert 0 < components.total_reward < 0.7
        # Partial success bonus
        assert 0 < components.success_bonus < calculator.config.success_bonus
    
    def test_failure_scenario(self):
        """Test complete failure scenario."""
        trace = ExecutionTrace(
            trace_id="",
            task_id="test-failure",
            timestamp="",
            problem_statement="Failed task"
        )
        
        trace.status = TraceStatus.ERROR
        trace.error = "RuntimeError: Something went wrong"
        trace.tests_passed = []
        trace.tests_failed = ["test_one", "test_two"]
        trace.execution_time_seconds = 5.0  # Failed quickly
        trace.iterations = 2
        
        calculator = RewardCalculator()
        components = calculator.compute_reward(trace)
        
        # Should have low or negative reward
        assert components.total_reward < 0.5
        # Error penalty applied
        assert components.penalty > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
