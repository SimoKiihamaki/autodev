# SWE-bench Lite Validation

This document describes how to run SWE-bench Lite benchmark validation for AutoDev.

## Overview

**SWE-bench Lite** is a curated subset of the SWE-bench dataset, containing approximately 300 real-world GitHub issues from popular Python repositories. It's designed for faster evaluation while maintaining representativeness of the full benchmark.

### Key Characteristics

- **Size**: ~300 instances (vs 2,294 in full SWE-bench)
- **Task**: Fix real-world bugs based on GitHub issue descriptions
- **Evaluation**: Tests must pass after applying the generated patch
- **Repositories**: Django, Flask, Requests, Pytest, and other popular Python projects

## Phase 10 Goal

**Target: 30%+ resolution rate on SWE-bench Lite**

This means successfully resolving at least 90 out of 300 instances.

## Requirements

### Python Dependencies

```bash
pip install datasets swebench-metrics
```

- `datasets`: HuggingFace library to load SWE-bench Lite dataset
- `swebench-metrics`: Official evaluation metrics for SWE-bench

### System Requirements

- Python 3.10+
- Git (for cloning test repositories)
- Sufficient disk space (~10GB for test repositories)
- Docker (optional, for isolated test environments)

## Quick Start

```bash
# Run a quick test with 5 instances
cd ~/Projects/autodev/scripts
python validate_swebench_lite.py --subset 5 --verbose

# Run a larger test with 50 instances
python validate_swebench_lite.py --subset 50

# Run full benchmark (takes hours)
python validate_swebench_lite.py
```

## Script Usage

### Command Line Options

```
python validate_swebench_lite.py [OPTIONS]

Options:
  --subset N        Run only N instances (default: all ~300)
  --output-dir DIR  Directory to save results (default: results/)
  --timeout N       Timeout per instance in seconds (default: 600)
  --verbose         Enable verbose logging
```

### Examples

```bash
# Quick smoke test
python validate_swebench_lite.py --subset 10 --verbose

# Production run with custom output
python validate_swebench_lite.py --output-dir ./benchmark_2024 --subset 100

# Full benchmark
python validate_swebench_lite.py --timeout 900
```

## Output

### Results File

Results are saved to `results/swebench_lite_results.json`:

```json
{
  "summary": {
    "total_instances": 300,
    "resolved_count": 90,
    "failed_count": 180,
    "timeout_count": 15,
    "error_count": 15,
    "resolution_rate": "30.00%",
    "avg_time_seconds": 45.2,
    "total_time_seconds": 13560.0,
    "timestamp": "2024-01-15T10:30:00"
  },
  "instances": [
    {
      "instance_id": "django__django-12345",
      "repo": "django/django",
      "resolved": true,
      "tests_passed": 10,
      "tests_failed": 0,
      "time_seconds": 32.5
    },
    ...
  ]
}
```

### Console Output

```
======================================================================
SWE-BENCH LITE VALIDATION SUMMARY
======================================================================
Timestamp: 2024-01-15T10:30:00

===============================RESULTS================================
Total Instances:     300
Resolved:            90
Failed:              180
Timeouts:            15
Errors:              15

===============================METRICS================================
Resolution Rate:     30.00%
Target (Phase 10):   30.00%
Status:              ✓ TARGET MET

===============================TIMING=================================
Average Time:        45.20s
Total Time:          13560.00s
======================================================================
```

## Integration with AutoDev

The validation script currently uses placeholder logic. To integrate with AutoDev:

### Step 1: Implement Patch Generation

Edit `validate_swebench_lite.py` and update the `_generate_patch_placeholder` method:

```python
def _generate_patch_placeholder(self, instance: dict) -> Optional[str]:
    """
    Integrate with AutoDev solver.
    
    Args:
        instance: SWE-bench instance with:
            - instance_id: Unique identifier
            - repo: Repository (e.g., "django/django")
            - problem_statement: Issue description
            - base_commit: Starting commit
            - hints_text: Optional hints
            
    Returns:
        Git diff patch string or None if generation failed
    """
    # Call AutoDev solver
    from autodev import AutoDevSolver
    
    solver = AutoDevSolver()
    patch = solver.solve_issue(
        repo=instance['repo'],
        commit=instance['base_commit'],
        problem=instance['problem_statement']
    )
    
    return patch
```

### Step 2: Implement Test Execution

Update the `run_single_instance` method to:

1. Clone the repository at base commit
2. Apply generated patch
3. Run test suite
4. Collect results

```python
def run_single_instance(self, instance: dict) -> BenchmarkResult:
    # Clone repo
    repo_dir = self._clone_repo(instance['repo'], instance['base_commit'])
    
    # Generate patch
    patch = self._generate_patch_placeholder(instance)
    
    # Apply patch
    applied = self._apply_patch(repo_dir, patch)
    
    # Run tests
    passed, failed = self._run_tests(repo_dir, instance['test_patch'])
    
    # Record results
    return BenchmarkResult(
        instance_id=instance['instance_id'],
        repo=instance['repo'],
        resolved=(failed == 0 and passed > 0),
        tests_passed=passed,
        tests_failed=failed,
        ...
    )
```

## SWE-bench Lite Dataset Structure

Each instance in the dataset contains:

```python
{
    "instance_id": "django__django-12345",
    "repo": "django/django",
    "version": "3.0",
    "base_commit": "abc123...",
    "problem_statement": "Description of the bug...",
    "hints_text": "Optional hints for solving...",
    "created_at": "2020-01-15T10:00:00",
    "patch": "Ground truth patch (for validation)",
    "test_patch": "Test file changes",
    "PASS_TO_PASS": ["test1", "test2"],  # Tests that should pass
    "FAIL_TO_PASS": ["test3"],           # Tests that should now pass
    "environment_setup_commit": "def456..."
}
```

## Evaluation Criteria

An instance is considered **resolved** if:

1. A valid patch is generated
2. The patch applies successfully
3. All `FAIL_TO_PASS` tests now pass
4. All `PASS_TO_PASS` tests still pass
5. No new test failures introduced

## Performance Tips

1. **Use caching**: Cache cloned repositories to avoid re-downloading
2. **Parallel execution**: Run multiple instances in parallel
3. **Timeout handling**: Set appropriate timeouts to avoid hanging
4. **Docker isolation**: Use Docker for clean test environments
5. **Selective testing**: Start with small subsets for faster iteration

## Troubleshooting

### Dataset Loading Errors

```bash
# Ensure you have internet access and HuggingFace credentials
huggingface-cli login
```

### Test Execution Failures

```bash
# Check repository setup
python validate_swebench_lite.py --subset 1 --verbose
```

### Timeout Issues

```bash
# Increase timeout for complex instances
python validate_swebench_lite.py --timeout 1200
```

## References

- [SWE-bench Paper](https://arxiv.org/abs/2310.06770)
- [SWE-bench GitHub](https://github.com/princeton-nlp/SWE-bench)
- [SWE-bench Lite Dataset](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Lite)
- [AutoDev Documentation](../README.md)

## Next Steps

1. ✅ Set up validation script infrastructure
2. ⬜ Integrate AutoDev solver into `_generate_patch_placeholder`
3. ⬜ Implement repository cloning and patch application
4. ⬜ Add test execution and validation logic
5. ⬜ Run initial benchmark (subset of 50)
6. ⬜ Optimize and iterate toward 30% goal
7. ⬜ Run full benchmark validation

## Maintenance

This script should be updated as:
- AutoDev's solver API evolves
- SWE-bench evaluation metrics change
- Performance improvements are implemented
