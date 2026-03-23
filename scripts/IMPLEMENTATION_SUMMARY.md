# SWE-bench Lite Validation Implementation Summary

## Task Completed

Research SWE-bench Lite benchmark requirements and create validation run script for AutoDev Phase 10 goal (30%+ resolution rate).

## What Was Created

### 1. Main Validation Script
**File:** `~/Projects/autodev/scripts/validate_swebench_lite.py`

A comprehensive standalone script that:
- Loads SWE-bench Lite dataset from HuggingFace (~300 instances)
- Runs validation with configurable subset sizes
- Reports detailed metrics (resolution rate, timing, errors)
- Saves results to JSON for analysis
- Provides colored console output with progress tracking
- Includes command-line interface with multiple options

**Key Features:**
- Configurable timeout per instance (default: 600s)
- Subset testing for faster iteration
- Verbose logging mode
- Automatic dependency checking
- JSON output with full instance details
- Progress updates every 10 instances

### 2. Python Module
**Directory:** `~/Projects/autodev/src/swebench/`

Created a reusable module with:
- `__init__.py` - Package initialization
- `runner.py` - Programmatic API for running benchmarks

**Runner Features:**
- `SWEbenchRunner` class with solver injection
- Dependency checking utilities
- Phase 10 status evaluation
- Result persistence
- Single instance execution

### 3. Documentation
**File:** `~/Projects/autodev/scripts/README_SWEBENCH.md`

Comprehensive documentation covering:
- SWE-bench Lite overview (300 instances, Python repos)
- Phase 10 goal: 30%+ resolution (90/300 instances)
- Installation requirements
- Quick start guide
- Integration instructions for AutoDev
- Evaluation criteria
- Performance tips
- Troubleshooting guide

### 4. Integration Example
**File:** `~/Projects/autodev/scripts/example_autodev_integration.py`

Demonstrates how to:
- Integrate AutoDev solver with validation runner
- Use the programmatic API
- Handle results and metrics
- Check Phase 10 status

### 5. Requirements File
**File:** `~/Projects/autodev/scripts/requirements_swebench.txt`

Dependencies:
- datasets>=2.14.0 (HuggingFace)
- swebench-metrics>=0.1.0 (evaluation)
- tqdm>=4.65.0 (progress bars)

## SWE-bench Lite Requirements (Research Findings)

### Dataset Specifications
- **Total Size:** ~300 instances
- **Source:** Real GitHub issues from popular Python repos
- **Repositories:** Django, Flask, Requests, Pytest, Astropy, etc.
- **Task:** Fix bugs based on issue descriptions
- **Evaluation:** Apply patch, run tests, verify all pass

### Instance Structure
Each instance contains:
```python
{
    "instance_id": "django__django-12345",
    "repo": "django/django",
    "version": "3.0",
    "base_commit": "abc123...",
    "problem_statement": "Bug description...",
    "hints_text": "Optional hints",
    "patch": "Ground truth patch",
    "test_patch": "Test changes",
    "PASS_TO_PASS": ["test1", "test2"],  # Should remain passing
    "FAIL_TO_PASS": ["test3"]            # Should now pass
}
```

### Evaluation Criteria
An instance is **resolved** if:
1. Valid patch is generated
2. Patch applies successfully
3. All FAIL_TO_PASS tests now pass
4. All PASS_TO_PASS tests still pass
5. No new failures introduced

### Phase 10 Goal
- **Target:** 30%+ resolution rate
- **Minimum:** 90 out of 300 instances resolved
- **Current Status:** Placeholder implementation (0%)

## How to Use

### Quick Test (5 instances)
```bash
cd ~/Projects/autodev/scripts
pip install datasets
python3 validate_swebench_lite.py --subset 5 --verbose
```

### Medium Test (50 instances)
```bash
python3 validate_swebench_lite.py --subset 50
```

### Full Benchmark (300 instances)
```bash
python3 validate_swebench_lite.py
```

### Programmatic Usage
```python
from swebench.runner import SWEbenchRunner

def my_solver(instance):
    # Call AutoDev solver
    return generated_patch

runner = SWEbenchRunner()
runner.set_solver(my_solver)
metrics = runner.run_benchmark(subset_size=50)

print(f"Resolution rate: {metrics['resolution_rate']:.2%}")
```

## Integration Points for AutoDev

### Primary Integration
Edit `validate_swebench_lite.py` method `_generate_patch_placeholder`:

```python
def _generate_patch_placeholder(self, instance: dict) -> Optional[str]:
    from autodev import AutoDevSolver
    
    solver = AutoDevSolver()
    return solver.solve_issue(
        repo=instance['repo'],
        commit=instance['base_commit'],
        problem=instance['problem_statement']
    )
```

### Secondary Steps
1. Implement repository cloning at base commit
2. Apply generated patch to cloned repo
3. Run test suite using `instance['test_patch']`
4. Collect pass/fail counts
5. Return results

## Testing Status

✅ **Verified Working:**
- Scripts execute without errors
- Help messages display correctly
- Dataset loads successfully from HuggingFace
- Example runs with real SWE-bench instances
- JSON output formatting works
- Progress tracking functional

⚠️ **Pending Implementation:**
- AutoDev solver integration
- Repository cloning logic
- Test execution framework
- Patch application validation

## File Structure

```
~/Projects/autodev/
├── scripts/
│   ├── validate_swebench_lite.py      # Main validation script
│   ├── example_autodev_integration.py # Integration example
│   ├── requirements_swebench.txt      # Dependencies
│   └── README_SWEBENCH.md            # Documentation
├── src/
│   └── swebench/
│       ├── __init__.py               # Package init
│       └── runner.py                 # Programmatic API
└── results/                          # Output directory (auto-created)
    └── swebench_lite_results.json    # Benchmark results
```

## Next Steps for Phase 10

1. **Install Dependencies**
   ```bash
   pip install -r scripts/requirements_swebench.txt
   ```

2. **Integrate AutoDev Solver**
   - Update `_generate_patch_placeholder` in validation script
   - Implement repo cloning and patch application
   - Add test execution logic

3. **Run Initial Validation**
   ```bash
   python3 scripts/validate_swebench_lite.py --subset 50
   ```

4. **Iterate and Improve**
   - Analyze failures
   - Tune solver parameters
   - Re-run with larger subsets

5. **Achieve 30% Target**
   - Run full 300 instance benchmark
   - Verify resolution rate ≥ 30%
   - Document results

## Metrics to Track

- **Resolution Rate:** % of instances where all tests pass
- **Patch Success Rate:** % of instances where patch applies
- **Average Time:** Seconds per instance
- **Timeout Rate:** % of instances that timeout
- **Error Rate:** % of instances with errors

## Conclusion

All infrastructure for SWE-bench Lite validation is now in place:
- ✅ Research completed on benchmark requirements
- ✅ Validation script created and tested
- ✅ Documentation provided
- ✅ Integration points identified
- ✅ Ready for AutoDev solver integration

The team can now proceed with integrating AutoDev's solver and running the benchmark to achieve the Phase 10 goal of 30%+ resolution rate.
