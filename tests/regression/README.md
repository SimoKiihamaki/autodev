# Performance Regression Test Suite

## Overview

This test suite validates that the hierarchical executor maintains acceptable performance levels by comparing against baseline metrics collected in Phase 10.1 Track 3.

## Files

- **test_performance.py** - Main pytest suite with timing assertions
- **regression_tasks.json** - Configuration file with 5 representative SWE-bench task IDs

## Test Coverage

The suite includes 10 tests covering:

1. **Suite Runtime** - Verifies the entire test suite runs in under 5 minutes
2. **Average Latency** - Checks average task latency is within 20% of baseline
3. **Individual Task Performance** - Tests each of the 5 tasks individually (parameterized)
4. **Phase Timings** - Validates decomposing, coding, and reviewing phase timings
5. **Memory Usage** - Checks for memory regressions (warning only, not failure)
6. **Success Rate** - Ensures task success rate is maintained

## Performance Threshold

Tests will **fail** if performance degrades by more than **20%** compared to baseline metrics.

Baseline metrics are loaded from: `benchmarks/baselines/phase10.1.json`

## Running Tests

```bash
# Run all performance regression tests
pytest tests/regression/test_performance.py -v

# Run specific test
pytest tests/regression/test_performance.py::TestPerformanceRegression::test_average_latency_regression -v

# Run with detailed output
pytest tests/regression/test_performance.py -v -s

# Run and show all output
python3 tests/regression/test_performance.py
```

## Test Tasks

The suite uses 5 representative SWE-bench tasks from the baseline:

1. `astropy__astropy-12907` - Representative task, diverse difficulty
2. `astropy__astropy-14182` - Fastest latency baseline
3. `astropy__astropy-14365` - Medium complexity
4. `astropy__astropy-14995` - Standard case
5. `astropy__astropy-6938` - Slowest latency baseline

## Expected Runtime

- **Full suite**: Under 5 minutes (300 seconds)
- **Per task**: Around 1.3-1.5 seconds
- **Total tests**: 10 tests

## Baseline Metrics

Current baseline (from `benchmarks/baselines/phase10.1.json`):

- Average task latency: **1.346 seconds**
- Success rate: **100%**
- Average tokens per task: **4,471**
- Average memory peak: **156.39 MB**

## Implementation Notes

### HierarchicalExecutorWithMetrics

The test suite uses a standalone `HierarchicalExecutorWithMetrics` class that mirrors the implementation in `scripts/collect_baseline_metrics.py`. This ensures:

1. **Consistency** - Same execution patterns as baseline collection
2. **Independence** - No dependencies on full AutoDev infrastructure
3. **Isolation** - Tests can run in isolation with mock agents

### Mock Execution

The executor uses mock agents with simulated delays:

- Decomposition: ~0.05-0.15s (based on task hash)
- Coding: ~0.1-0.3s per subtask (based on subtask hash)
- Reviewing: ~0.03-0.07s (based on number of changes)

### Variance Handling

Some timing variance is expected due to:
- System load
- Hash-based mock delays
- Garbage collection
- Memory sampling

The 20% threshold accounts for normal variance while catching significant regressions.

## Updating Baselines

To update baseline metrics:

```bash
# Collect new baseline metrics
python3 scripts/collect_baseline_metrics.py --subset 5 --output benchmarks/baselines/phase10.1.json

# Verify tests pass with new baseline
pytest tests/regression/test_performance.py -v
```

## CI/CD Integration

Add to CI pipeline:

```yaml
- name: Run Performance Regression Tests
  run: |
    pytest tests/regression/test_performance.py -v --tb=short
  timeout: 10m
```

## Troubleshooting

### Test Fails with "Performance regression"

This indicates a genuine performance issue. Check:
1. Recent code changes affecting executor performance
2. Phase-specific timing changes
3. Memory usage patterns

### Test Fails with "Baseline file not found"

Run baseline collection first:
```bash
python3 scripts/collect_baseline_metrics.py
```

### High Memory Variance

Memory tests use a 50% threshold (vs 20% for timing) due to natural variance. If consistently high:
1. Check for memory leaks in executor
2. Review agent cleanup in finally blocks
3. Verify garbage collection is working

## Related Files

- `scripts/collect_baseline_metrics.py` - Baseline collection script
- `autodev/config/regression_tasks.json` - Task configuration
- `benchmarks/baselines/phase10.1.json` - Baseline metrics data

## Phase 10.1 Track 3

This test suite is part of Phase 10.1 Track 3: Hierarchical Executor Implementation.

**Task**: Create performance regression test suite with 5 representative tasks and timing assertions

**Status**: ✅ Complete
