# AutoDev Phase 7: SWE-bench Test Harness

**Version:** 7.0.0  
**Created:** 2026-03-23  
**Status:** Complete  
**Depends On:** Phase 6 (Hermes Tool Integration)

---

## Executive Summary

Phase 7 implements a comprehensive SWE-bench test harness for validating the AutoDev pipeline against real-world GitHub issue resolution tasks. The harness provides:

- **Task Loading**: Load tasks from SWE-bench Lite, Full, or Verified datasets
- **Pipeline Execution**: Run AutoDevPipeline against each task
- **Resolution Tracking**: Measure resolution rate against 20%+ target
- **Pattern Analysis**: Identify success/failure patterns for improvement
- **Reporting**: Generate detailed reports and cost analysis

---

## Components

### 1. Main Harness (`src/benchmark/swe_bench_harness.py`)

The core test harness that orchestrates evaluation:

```python
from benchmark.swe_bench_harness import SWEBenchHarness

harness = SWEBenchHarness(
    workspace="/tmp/swebench_workspace",
    timeout_seconds=1800,
    max_iterations=30
)

results = await harness.run_evaluation(
    subset="lite",
    num_tasks=10
)

print(f"Resolution rate: {results.resolution_rate:.1%}")
```

#### Key Classes

**`SWEBenchHarness`**
- Loads tasks from Hugging Face datasets
- Sets up workspace (clones repos at correct commits)
- Executes AutoDevPipeline on each task
- Tracks patterns and aggregates results

**`SWETask`**
- Represents a single SWE-bench task
- Contains issue description, repo, commit, tests

**`TaskResult`**
- Result of evaluating a single task
- Status, execution time, tokens, tools used

**`EvaluationResults`**
- Aggregated results across all tasks
- Resolution rate, cost estimate, patterns

### 2. Verification Module (`src/benchmark/verification.py`)

Patch and test verification:

```python
from benchmark.verification import PatchVerifier

verifier = PatchVerifier(workspace_path)
result = verifier.verify_resolution(
    fail_to_pass=["test_query", "test_orm"],
    pass_to_pass=["test_basic"]
)
```

#### Features
- Apply patches to workspace
- Compare generated vs gold patches
- Run pytest tests
- Verify FAIL_TO_PASS and PASS_TO_PASS tests

### 3. Reporting Module (`src/benchmark/reporting.py`)

Generate analysis reports:

```python
from benchmark.reporting import ResultsReporter

reporter = ResultsReporter(results.to_dict())
report = reporter.generate_markdown_report()
reporter.save_report(Path("report.md"))
```

#### Report Sections
- Executive Summary with key metrics
- Resolution Analysis by status and repository
- Performance Analysis (tokens, time, cost)
- Pattern Analysis (tools, failure reasons)
- Task Details
- Recommendations

---

## Usage

### CLI Runner

```bash
# Run 10 tasks from SWE-bench Lite
python -m benchmark.run_swe_bench --num-tasks 10 --subset lite

# Run specific tasks
python -m benchmark.run_swe_bench --task-ids django__django-12345

# Parallel execution
python -m benchmark.run_swe_bench --num-tasks 20 --parallel

# Use different model
python -m benchmark.run_swe_bench --model claude-3-opus-20240229
```

### Programmatic Usage

```python
import asyncio
from benchmark import SWEBenchHarness

async def evaluate():
    harness = SWEBenchHarness(
        workspace="/tmp/swebench",
        max_iterations=30
    )
    
    results = await harness.run_evaluation(
        subset="lite",
        num_tasks=50
    )
    
    print(f"Resolution Rate: {results.resolution_rate:.1%}")
    print(f"Total Cost: ${results.total_cost_estimate:.2f}")
    
    # Check if target met
    if results.resolution_rate >= 0.20:
        print("✅ Target achieved!")
    else:
        print("❌ Below 20% target")

asyncio.run(evaluate())
```

---

## Configuration Options

### Harness Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `workspace` | `/tmp/swebench_workspace` | Base directory for task workspaces |
| `timeout_seconds` | 1800 | Max time per task (30 min) |
| `max_iterations` | 30 | Max tool iterations per task |
| `api_key` | env `ANTHROPIC_API_KEY` | Anthropic API key |
| `model` | `claude-3-5-sonnet-20241022` | LLM model to use |

### Evaluation Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `subset` | `lite` | Dataset: lite, full, verified |
| `num_tasks` | None | Max tasks to evaluate |
| `task_ids` | None | Specific task IDs |
| `parallel` | False | Run tasks in parallel |
| `max_parallel` | 3 | Max concurrent tasks |

---

## Target Metrics

### Primary Target: 20%+ Resolution Rate

SWE-bench resolution rates across systems:
- Claude 3.5 Sonnet + OpenHands: ~30%
- GPT-4o + Aider: ~26%
- AutoCodeRover: ~20%
- **AutoDev Target**: 20%+

### Secondary Metrics

| Metric | Target |
|--------|--------|
| Avg Execution Time | < 300s |
| Error Rate | < 10% |
| Timeout Rate | < 5% |
| Cost per Resolution | < $1.00 |

---

## Result Analysis

### Pattern Tracking

The harness automatically tracks:

**Success Patterns:**
- Tools used in successful resolutions
- Files modified
- Iteration counts
- Repository-specific success rates

**Failure Patterns:**
- Common error messages
- Repositories with low success rates
- Tasks hitting iteration limits

### Example Patterns Output

```python
{
    "success_rate_by_repo": {
        "django/django": 0.25,
        "flask-admin/flask-admin": 0.15
    },
    "common_success_tools": {
        "read_file": 45,
        "write_file": 42,
        "execute_command": 38
    },
    "common_failure_reasons": {
        "Max iterations reached": 12,
        "Timeout": 5
    },
    "avg_iterations_success": 8.5,
    "avg_iterations_failure": 18.2
}
```

---

## Output Files

### Results Directory Structure

```
/tmp/swebench_workspace/
└── results/
    ├── evaluation_20260323_051600.json    # Full results
    ├── evaluation_report.md                # Markdown report
    ├── latest_summary.txt                  # Quick summary
    └── intermediate_results.json           # Progress tracking
```

### JSON Results Format

```json
{
    "total_tasks": 10,
    "resolved": 2,
    "failed": 5,
    "errors": 2,
    "timeouts": 1,
    "resolution_rate": 0.2,
    "avg_execution_time": 145.5,
    "total_tokens": {
        "total_tokens": 150000,
        "input_tokens": 100000,
        "output_tokens": 50000
    },
    "total_cost_estimate": 1.05,
    "patterns": {...},
    "task_results": [...]
}
```

---

## Testing

### Unit Tests

```bash
# Run all tests
pytest src/benchmark/test_swe_bench_harness.py -v

# Run with coverage
pytest src/benchmark/test_swe_bench_harness.py --cov=benchmark
```

### Test Categories

1. **SWETask Tests** - Task data structure
2. **TaskResult Tests** - Result data structure
3. **EvaluationResults Tests** - Aggregation
4. **Harness Tests** - Core functionality
5. **Verification Tests** - Patch verification
6. **Reporting Tests** - Report generation
7. **Integration Tests** - End-to-end

---

## Prerequisites

### Required Packages

```bash
pip install datasets anthropic pytest pytest-asyncio
```

### Environment Variables

```bash
export ANTHROPIC_API_KEY="your-key-here"
```

### MCP Configuration

Ensure MCP servers are configured at `~/.config/autodev/mcp_config.json`:

```json
{
    "servers": [
        {"name": "filesystem", "enabled": true},
        {"name": "terminal", "enabled": true},
        {"name": "git", "enabled": true}
    ]
}
```

---

## Troubleshooting

### Common Issues

**1. Dataset Loading Fails**
```
Solution: pip install datasets
```

**2. Git Clone Timeout**
```
Solution: Increase timeout or check network connection
```

**3. API Key Error**
```
Solution: export ANTHROPIC_API_KEY="your-key"
```

**4. MCP Connection Error**
```
Solution: Check MCP config and ensure servers are running
```

### Debug Mode

```bash
# Enable verbose logging
python -m benchmark.run_swe_bench --verbose --num-tasks 1

# Dry run to check config
python -m benchmark.run_swe_bench --dry-run
```

---

## Future Enhancements

### Phase 8 Integration
- RL training data collection
- GRPO reward signal from resolution outcomes
- Model fine-tuning pipeline

### Planned Improvements
1. **Caching**: Cache cloned repos between runs
2. **Resume**: Resume interrupted evaluations
3. **Distributed**: Run across multiple machines
4. **Real-time**: Live progress dashboard
5. **A/B Testing**: Compare model configurations

---

## Files Created

| File | Purpose |
|------|---------|
| `src/benchmark/__init__.py` | Module exports |
| `src/benchmark/swe_bench_harness.py` | Main harness (28KB) |
| `src/benchmark/verification.py` | Patch verification (10KB) |
| `src/benchmark/reporting.py` | Report generation (11KB) |
| `src/benchmark/test_swe_bench_harness.py` | Unit tests (14KB) |
| `src/benchmark/run_swe_bench.py` | CLI runner (7KB) |

---

## Summary

Phase 7 delivers a production-ready SWE-bench test harness that:

✅ Loads tasks from Hugging Face datasets  
✅ Runs AutoDevPipeline against each task  
✅ Measures resolution rate against 20% target  
✅ Tracks success/failure patterns  
✅ Generates comprehensive reports  
✅ Estimates costs and token usage  
✅ Supports parallel execution  
✅ Provides CLI and programmatic interfaces  

**Target: 20%+ SWE-bench resolution rate**

---

*Last updated: 2026-03-23 (Phase 7 Complete - SWE-bench Test Harness)*
