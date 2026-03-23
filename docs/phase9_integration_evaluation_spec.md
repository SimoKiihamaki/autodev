# AutoDev Phase 9: Integration & Evaluation

**Version:** 9.0.0  
**Created:** 2026-03-23  
**Status:** Planning  
**Depends On:** Phase 7 (SWE-bench Test Harness), Phase 8 (RL Training Pipeline)

---

## Executive Summary

Phase 9 integrates the RL training pipeline (Phase 8) with the SWE-bench evaluation harness (Phase 7) to enable end-to-end model improvement and validation. This phase delivers the production infrastructure needed to:

1. **Run Training Pipelines** - Execute full GRPO training with collected traces
2. **Evaluate Trained Models** - Benchmark fine-tuned models against SWE-bench
3. **Track Progress** - Monitor training and evaluation metrics toward 25%+ target
4. **Deploy Models** - Integrate fine-tuned models back into AutoDev pipeline
5. **Validate Integration** - End-to-end integration tests across all components

### Target Metrics

| Metric | Baseline (Phase 7) | Target (Phase 9) |
|--------|-------------------|------------------|
| SWE-bench Resolution Rate | 20% | 25%+ |
| Training Pipeline Uptime | N/A | 99% |
| Evaluation Cycle Time | N/A | <24 hours for 50 tasks |
| Model Deployment Time | N/A | <30 minutes |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Phase 9: Integration & Evaluation                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     Training Pipeline Orchestration                   │   │
│  │  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌──────────┐  │   │
│  │  │ Data        │   │ Reward      │   │ GRPO        │   │ Model    │  │   │
│  │  │ Collector   │──▶│ Calculator  │──▶│ Trainer     │──▶│ Registry │  │   │
│  │  │ (Phase 8)   │   │ (Phase 8)   │   │ (Phase 8)   │   │(Phase 8) │  │   │
│  │  └─────────────┘   └─────────────┘   └─────────────┘   └──────────┘  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│           │                                              │                   │
│           ▼                                              ▼                   │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     Evaluation & Deployment                          │   │
│  │  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌──────────┐  │   │
│  │  │ SWE-bench   │   │ Metrics     │   │ Model       │   │ AutoDev  │  │   │
│  │  │ Harness     │   │ Dashboard   │   │ Deployer    │   │ Pipeline │  │   │
│  │  │ (Phase 7)   │   │ (NEW)       │   │ (NEW)       │   │ (Updated)│  │   │
│  │  └─────────────┘   └─────────────┘   └─────────────┘   └──────────┘  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     Integration Tests (NEW)                          │   │
│  │  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                 │   │
│  │  │ E2E Tests   │   │ Stress      │   │ Regression  │                 │   │
│  │  │             │   │ Tests       │   │ Tests       │                 │   │
│  │  └─────────────┘   └─────────────┘   └─────────────┘                 │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. Training Pipeline Orchestrator (`src/training/orchestrator.py`)

Coordinates the full training workflow from data collection to model registration.

```python
from training.orchestrator import TrainingOrchestrator, OrchestratorConfig

config = OrchestratorConfig(
    data_collection_episodes=100,
    min_traces_for_training=50,
    evaluation_interval=100,
    checkpoint_dir="~/.autodev/checkpoints",
    model_output_dir="~/.autodev/models"
)

orchestrator = TrainingOrchestrator(config)

# Run full training cycle
result = await orchestrator.run_training_cycle(
    base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
    swebench_subset="lite",
    num_eval_tasks=50
)

print(f"Model trained: {result.model_path}")
print(f"Resolution rate: {result.resolution_rate:.1%}")
```

#### Key Classes

**`TrainingOrchestrator`**
- Coordinates data collection, training, and evaluation
- Manages checkpoints and recovery
- Handles distributed training setup
- Provides progress reporting

**`OrchestratorConfig`**
- Training configuration with sensible defaults
- Resource limits (GPU, memory, time)
- Checkpoint and output paths

**`TrainingCycleResult`**
- Result of a complete training cycle
- Model path, metrics, evaluation results
- Comparison with baseline

---

### 2. SWE-bench Evaluation Runner (`src/evaluation/swebench_runner.py`)

Production-ready evaluation runner for benchmarking trained models.

```python
from evaluation.swebench_runner import SWEBenchRunner, RunnerConfig

runner = SWEBenchRunner(
    model_path="~/.autodev/models/grpo_v1",
    workspace="/tmp/swebench_eval",
    max_concurrent=4
)

# Run evaluation
results = await runner.evaluate(
    subset="lite",
    num_tasks=50,
    timeout_per_task=1800
)

# Generate report
report = runner.generate_report(results)
report.save("~/eval_reports/eval_2026-03-23.md")

# Compare with baseline
comparison = await runner.compare_with_baseline(
    baseline_model="Qwen/Qwen2.5-Coder-7B-Instruct",
    tasks=results.task_ids
)
```

#### Features

- **Parallel Execution**: Run multiple task evaluations concurrently
- **Checkpoint/Resume**: Resume interrupted evaluations
- **Cost Tracking**: Track API costs and token usage
- **Error Recovery**: Automatic retry with backoff
- **Report Generation**: Markdown and JSON reports

---

### 3. Metrics Dashboard (`src/metrics/dashboard.py`)

Real-time metrics tracking and visualization for training and evaluation.

```python
from metrics.dashboard import MetricsDashboard, DashboardConfig

dashboard = MetricsDashboard(
    storage_backend="sqlite",  # or "postgres" for production
    db_path="~/.autodev/metrics.db"
)

# Track training progress
dashboard.log_training_step(
    step=100,
    loss=0.324,
    reward_mean=0.72,
    kl_divergence=0.05
)

# Track evaluation results
dashboard.log_evaluation_result(
    model_version="grpo_v1",
    task_id="django__django-12345",
    resolved=True,
    execution_time=234.5
)

# Query metrics
summary = dashboard.get_summary(model_version="grpo_v1")
print(f"Resolution rate: {summary.resolution_rate:.1%}")
print(f"Avg execution time: {summary.avg_execution_time:.1f}s")

# Export for analysis
dashboard.export_metrics(format="csv", path="metrics.csv")
```

#### Features

- **Time-Series Storage**: Efficient storage of metrics over time
- **Aggregation Queries**: Fast summary statistics
- **Export Formats**: CSV, JSON, Parquet
- **Comparison Views**: Compare multiple model versions
- **Alert Thresholds**: Configurable alerts for metric degradation

---

### 4. Model Deployer (`src/deployment/model_deployer.py`)

Deploy fine-tuned models to AutoDev pipeline with validation.

```python
from deployment.model_deployer import ModelDeployer, DeploymentConfig

deployer = ModelDeployer(
    registry_path="~/.autodev/models",
    pipeline_config_path="~/.autodev/config.yaml"
)

# Validate model before deployment
validation = await deployer.validate_model(
    model_path="~/.autodev/models/grpo_v1",
    test_tasks=["django__django-12345", "pytest__pytest-6789"]
)

if validation.passed:
    # Deploy to pipeline
    deployment = await deployer.deploy(
        model_path="~/.autodev/models/grpo_v1",
        strategy="canary",  # or "immediate", "blue-green"
        canary_percentage=10
    )
    
    print(f"Deployed: {deployment.model_id}")
    print(f"Status: {deployment.status}")
```

#### Features

- **Pre-deployment Validation**: Run smoke tests before deployment
- **Deployment Strategies**: Canary, blue-green, immediate
- **Rollback Support**: Automatic rollback on failure
- **Health Checks**: Post-deployment health monitoring
- **Version Management**: Track deployed model versions

---

### 5. Integration Test Suite (`tests/integration/`)

Comprehensive end-to-end tests validating the full pipeline.

#### Test Categories

**A. Data Flow Tests (`tests/integration/test_data_flow.py`)**

```python
class TestDataFlow:
    """Tests for data collection through training flow."""
    
    async def test_trace_collection_to_training(self):
        """Verify traces flow correctly to training dataset."""
        # 1. Run SWE-bench task
        # 2. Collect execution trace
        # 3. Verify trace format
        # 4. Verify reward calculation
        # 5. Verify dataset creation
        
    async def test_reward_calculation_pipeline(self):
        """Test reward calculation for various outcomes."""
        # Test success, failure, timeout scenarios
        # Verify reward components are calculated correctly
```

**B. Training Pipeline Tests (`tests/integration/test_training_pipeline.py`)**

```python
class TestTrainingPipeline:
    """Tests for GRPO training pipeline."""
    
    async def test_full_training_cycle(self):
        """Test complete training cycle with mock data."""
        # Use mock traces
        # Run training for 10 steps
        # Verify model checkpoint created
        # Verify metrics logged
        
    async def test_checkpoint_recovery(self):
        """Test resuming training from checkpoint."""
        # Start training
        # Simulate crash at step 5
        # Resume from checkpoint
        # Verify training continues correctly
```

**C. Evaluation Tests (`tests/integration/test_evaluation.py`)**

```python
class TestEvaluation:
    """Tests for SWE-bench evaluation."""
    
    async def test_evaluation_with_trained_model(self):
        """Test evaluation pipeline with fine-tuned model."""
        # Load trained model
        # Run 5 task evaluation
        # Verify results format
        # Verify report generation
        
    async def test_baseline_comparison(self):
        """Test comparison between baseline and trained model."""
        # Run baseline evaluation
        # Run trained model evaluation
        # Compare results
        # Verify improvement metrics
```

**D. Deployment Tests (`tests/integration/test_deployment.py`)**

```python
class TestDeployment:
    """Tests for model deployment."""
    
    async def test_model_validation(self):
        """Test pre-deployment validation."""
        # Create test model
        # Run validation
        # Verify validation result
        
    async def test_deployment_rollback(self):
        """Test automatic rollback on failure."""
        # Deploy model
        # Simulate failure in health check
        # Verify rollback triggered
```

---

### 6. CLI Scripts (`scripts/`)

Production command-line tools for training and evaluation.

#### `scripts/run_training.py`

```bash
# Run full training cycle
python scripts/run_training.py \
    --base-model Qwen/Qwen2.5-Coder-7B-Instruct \
    --episodes 100 \
    --eval-tasks 50 \
    --output ~/.autodev/models/grpo_v1

# Resume from checkpoint
python scripts/run_training.py \
    --resume ~/.autodev/checkpoints/training_2026-03-23

# Dry run (no actual training)
python scripts/run_training.py \
    --dry-run \
    --episodes 10
```

#### `scripts/run_evaluation.py`

```bash
# Evaluate model on SWE-bench
python scripts/run_evaluation.py \
    --model ~/.autodev/models/grpo_v1 \
    --subset lite \
    --num-tasks 50 \
    --output eval_results.json

# Compare with baseline
python scripts/run_evaluation.py \
    --model ~/.autodev/models/grpo_v1 \
    --baseline Qwen/Qwen2.5-Coder-7B-Instruct \
    --num-tasks 50 \
    --compare

# Generate report
python scripts/run_evaluation.py \
    --model ~/.autodev/models/grpo_v1 \
    --report-format markdown \
    --report-output eval_report.md
```

#### `scripts/deploy_model.py`

```bash
# Deploy model to pipeline
python scripts/deploy_model.py \
    --model ~/.autodev/models/grpo_v1 \
    --strategy canary \
    --canary-percent 10

# Rollback deployment
python scripts/deploy_model.py \
    --rollback \
    --to-version grpo_v0
```

---

## Implementation Plan

### Week 1: Core Infrastructure

#### Day 1-2: Training Orchestrator
- [ ] Create `src/training/orchestrator.py` with `TrainingOrchestrator` class
- [ ] Implement `run_training_cycle()` method
- [ ] Add checkpoint/recovery support
- [ ] Write unit tests

#### Day 3-4: SWE-bench Runner
- [ ] Create `src/evaluation/swebench_runner.py`
- [ ] Implement parallel task execution
- [ ] Add checkpoint/resume for evaluations
- [ ] Integrate with Phase 7 harness
- [ ] Write unit tests

#### Day 5: Metrics Dashboard (Core)
- [ ] Create `src/metrics/dashboard.py` with SQLite backend
- [ ] Implement metric logging functions
- [ ] Add summary queries
- [ ] Write unit tests

### Week 2: Integration & Deployment

#### Day 1-2: Model Deployer
- [ ] Create `src/deployment/model_deployer.py`
- [ ] Implement validation logic
- [ ] Add deployment strategies (canary, blue-green)
- [ ] Implement rollback
- [ ] Write unit tests

#### Day 3-4: Integration Tests
- [ ] Create `tests/integration/` structure
- [ ] Write data flow tests
- [ ] Write training pipeline tests
- [ ] Write evaluation tests
- [ ] Write deployment tests

#### Day 5: CLI Scripts
- [ ] Create `scripts/run_training.py`
- [ ] Create `scripts/run_evaluation.py`
- [ ] Create `scripts/deploy_model.py`
- [ ] Add documentation

### Week 3: Production Readiness

#### Day 1-2: End-to-End Testing
- [ ] Run full training cycle on 10 tasks
- [ ] Verify checkpoint/recovery
- [ ] Test deployment pipeline
- [ ] Validate metrics collection

#### Day 3-4: Evaluation Runs
- [ ] Run baseline evaluation (Qwen2.5-Coder-7B)
- [ ] Train model with 100 episodes
- [ ] Evaluate trained model on 50 tasks
- [ ] Compare results

#### Day 5: Documentation & Polish
- [ ] Update ARCHITECTURE.md
- [ ] Create evaluation run reports
- [ ] Document CLI usage
- [ ] Create troubleshooting guide

---

## File Structure

```
src/
├── training/
│   ├── __init__.py              # Update exports
│   ├── orchestrator.py          # NEW: Training orchestration
│   ├── data_collector.py        # Phase 8
│   ├── reward_calculator.py     # Phase 8
│   ├── grpo_trainer.py          # Phase 8
│   ├── model_registry.py        # Phase 8
│   └── pipeline.py              # Phase 8
│
├── evaluation/
│   ├── __init__.py              # NEW
│   ├── swebench_runner.py       # NEW: Evaluation runner
│   └── comparison.py            # NEW: Baseline comparison
│
├── metrics/
│   ├── __init__.py              # NEW
│   ├── dashboard.py             # NEW: Metrics tracking
│   ├── storage.py               # NEW: Storage backends
│   └── exporters.py             # NEW: Export utilities
│
├── deployment/
│   ├── __init__.py              # NEW
│   ├── model_deployer.py        # NEW: Model deployment
│   ├── validation.py            # NEW: Pre-deployment checks
│   └── strategies.py            # NEW: Deployment strategies
│
└── benchmark/                   # Phase 7 (existing)
    ├── swe_bench_harness.py
    ├── verification.py
    └── reporting.py

tests/
├── integration/
│   ├── __init__.py              # NEW
│   ├── test_data_flow.py        # NEW
│   ├── test_training_pipeline.py # NEW
│   ├── test_evaluation.py       # NEW
│   └── test_deployment.py       # NEW
│
└── unit/
    ├── test_orchestrator.py     # NEW
    ├── test_swebench_runner.py  # NEW
    ├── test_dashboard.py        # NEW
    └── test_deployer.py         # NEW

scripts/
├── run_training.py              # NEW
├── run_evaluation.py            # NEW
└── deploy_model.py              # NEW
```

---

## API Reference

### TrainingOrchestrator

```python
class TrainingOrchestrator:
    def __init__(self, config: OrchestratorConfig): ...
    
    async def run_training_cycle(
        self,
        base_model: str,
        swebench_subset: str = "lite",
        num_eval_tasks: int = 50,
        resume_from: Optional[str] = None
    ) -> TrainingCycleResult: ...
    
    async def collect_training_data(
        self,
        num_episodes: int,
        tasks: Optional[List[str]] = None
    ) -> CollectionResult: ...
    
    async def train_model(
        self,
        traces_path: str,
        output_path: str
    ) -> TrainingResult: ...
    
    async def evaluate_model(
        self,
        model_path: str,
        num_tasks: int
    ) -> EvaluationResult: ...
    
    def get_checkpoint(self) -> OrchestratorCheckpoint: ...
    
    async def resume_from_checkpoint(
        self,
        checkpoint_path: str
    ) -> None: ...
```

### SWEBenchRunner

```python
class SWEBenchRunner:
    def __init__(
        self,
        model_path: str,
        workspace: str,
        max_concurrent: int = 4
    ): ...
    
    async def evaluate(
        self,
        subset: str = "lite",
        num_tasks: int = 50,
        timeout_per_task: int = 1800,
        resume_from: Optional[str] = None
    ) -> EvaluationResults: ...
    
    async def evaluate_single_task(
        self,
        task_id: str
    ) -> TaskResult: ...
    
    async def compare_with_baseline(
        self,
        baseline_model: str,
        tasks: Optional[List[str]] = None
    ) -> ComparisonResult: ...
    
    def generate_report(
        self,
        results: EvaluationResults,
        format: str = "markdown"
    ) -> Report: ...
```

### MetricsDashboard

```python
class MetricsDashboard:
    def __init__(
        self,
        storage_backend: str = "sqlite",
        db_path: str = "~/.autodev/metrics.db"
    ): ...
    
    def log_training_step(
        self,
        step: int,
        loss: float,
        reward_mean: float,
        kl_divergence: float,
        **kwargs
    ) -> None: ...
    
    def log_evaluation_result(
        self,
        model_version: str,
        task_id: str,
        resolved: bool,
        execution_time: float,
        **kwargs
    ) -> None: ...
    
    def get_summary(
        self,
        model_version: str
    ) -> MetricsSummary: ...
    
    def get_resolution_rate_history(
        self,
        model_versions: List[str]
    ) -> pd.DataFrame: ...
    
    def export_metrics(
        self,
        format: str = "csv",
        path: str = None
    ) -> None: ...
```

### ModelDeployer

```python
class ModelDeployer:
    def __init__(
        self,
        registry_path: str,
        pipeline_config_path: str
    ): ...
    
    async def validate_model(
        self,
        model_path: str,
        test_tasks: List[str]
    ) -> ValidationResult: ...
    
    async def deploy(
        self,
        model_path: str,
        strategy: str = "canary",
        canary_percentage: int = 10
    ) -> Deployment: ...
    
    async def rollback(
        self,
        to_version: str
    ) -> Deployment: ...
    
    def get_deployment_status(
        self,
        deployment_id: str
    ) -> DeploymentStatus: ...
```

---

## Configuration

### `~/.autodev/config.yaml` additions

```yaml
# Phase 9 configuration
training:
  orchestrator:
    checkpoint_dir: ~/.autodev/checkpoints
    model_output_dir: ~/.autodev/models
    min_traces_for_training: 50
    evaluation_interval: 100
    
  resources:
    gpu_memory_fraction: 0.8
    max_training_hours: 24
    
evaluation:
  runner:
    max_concurrent: 4
    timeout_per_task: 1800
    workspace: /tmp/swebench_eval
    
metrics:
  dashboard:
    storage_backend: sqlite
    db_path: ~/.autodev/metrics.db
    
deployment:
  default_strategy: canary
  canary_percentage: 10
  health_check_interval: 60
  rollback_threshold: 0.15  # 15% error rate triggers rollback
```

---

## Success Criteria

### Phase 9 Complete When:

- [ ] Training orchestrator operational with checkpoint/recovery
- [ ] SWE-bench runner supports parallel evaluation
- [ ] Metrics dashboard tracks training and evaluation
- [ ] Model deployer supports canary deployment
- [ ] Integration test suite passes (>90% coverage)
- [ ] CLI scripts documented and functional
- [ ] First training cycle completed successfully
- [ ] Evaluation shows improvement over baseline
- [ ] Documentation updated (ARCHITECTURE.md, README.md)

### Stretch Goals:

- [ ] 25%+ SWE-bench resolution rate achieved
- [ ] Continuous learning loop operational
- [ ] Web-based metrics dashboard (optional)
- [ ] Multi-GPU training support
- [ ] Integration with W&B or MLflow

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Training data insufficiency | Low improvement | Collect 100+ traces before training |
| GPU resource constraints | Slow iteration | Use gradient checkpointing, LoRA |
| Evaluation instability | Inconsistent results | Run multiple evaluation rounds |
| Deployment failures | Pipeline downtime | Blue-green deployment, health checks |
| Metrics storage growth | Disk space | Implement retention policy |

---

## Dependencies

### Python Packages

```
# Already installed (Phase 7, 8)
datasets>=2.14.0
transformers>=4.36.0
trl>=0.7.0
torch>=2.1.0
pydantic>=2.0.0

# New for Phase 9
aiohttp>=3.9.0       # Async HTTP for parallel evaluation
sqlalchemy>=2.0.0    # Metrics storage
pandas>=2.0.0        # Metrics analysis
```

### System Requirements

- GPU: NVIDIA GPU with 16GB+ VRAM for training
- Storage: 50GB+ for models and checkpoints
- Memory: 32GB+ RAM for parallel evaluation

---

## References

- Phase 7 Spec: `docs/phase7_swe_bench_harness.md`
- Phase 8 Spec: `docs/phase8_rl_training_spec.md`
- Architecture: `docs/ARCHITECTURE.md`
- TRL Documentation: https://huggingface.co/docs/trl
