# AutoDev Phase 8: RL Training Integration with GRPO Pipeline

**Version:** 8.0.0  
**Created:** 2026-03-23  
**Status:** Planning  
**Depends On:** Phase 7 (SWE-bench Test Harness)

---

## Executive Summary

Phase 8 implements Reinforcement Learning (RL) training integration using Group Relative Policy Optimization (GRPO) to improve the AutoDev pipeline's code generation capabilities. The integration leverages execution-based rewards from SWE-bench resolution outcomes to fine-tune code models.

### Goals

1. **Training Data Collection**: Gather execution traces from SWE-bench runs
2. **Reward Signal Design**: Implement multi-component reward functions
3. **TRL Integration**: Integrate Hugging Face TRL's GRPO trainer
4. **Model Fine-tuning**: Create pipeline for GRPO-based model improvement
5. **Continuous Learning**: Enable self-improvement through feedback loops

### Target Metrics

| Metric | Baseline | Target |
|--------|----------|--------|
| SWE-bench Resolution Rate | 20% | 25%+ |
| Code Quality Score | TBD | +15% improvement |
| Test Pass Rate | TBD | +20% improvement |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Phase 8: RL Training                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐   │
│  │  SWE-bench       │    │  Training Data   │    │   GRPO Trainer   │   │
│  │  Harness         │───▶│  Collector       │───▶│   (TRL-based)    │   │
│  │  (Phase 7)       │    │                  │    │                  │   │
│  └──────────────────┘    └──────────────────┘    └──────────────────┘   │
│           │                       │                       │              │
│           ▼                       ▼                       ▼              │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐   │
│  │  Execution       │    │  Reward          │    │  Fine-tuned      │   │
│  │  Traces          │    │  Calculator      │    │  Model           │   │
│  └──────────────────┘    └──────────────────┘    └──────────────────┘   │
│                                   │                       │              │
│                                   ▼                       ▼              │
│                          ┌──────────────────┐    ┌──────────────────┐   │
│                          │  Reward Signals  │    │  Model Registry  │   │
│                          │  (Multi-comp)    │    │  & Versioning    │   │
│                          └──────────────────┘    └──────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. Training Data Collector (`src/training/data_collector.py`)

Collects execution traces from AutoDev pipeline runs for training.

```python
from training.data_collector import TrainingDataCollector

collector = TrainingDataCollector(
    output_dir="~/.autodev/training_data",
    max_traces_per_task=10,
    include_failed_attempts=True
)

# Integrated with SWE-bench harness
await collector.collect_from_evaluation(
    harness=SWEBenchHarness(...),
    num_tasks=100
)
```

#### Key Classes

**`ExecutionTrace`**
- Complete execution history of a task attempt
- LLM prompts and responses
- Tool calls and results
- Final outcome (success/failure)

**`TrainingDataCollector`**
- Captures traces from pipeline execution
- Stores in efficient format (parquet/jsonl)
- Supports filtering by outcome, task type, etc.

#### Data Schema

```python
@dataclass
class ExecutionTrace:
    trace_id: str
    task_id: str
    timestamp: datetime
    
    # Input
    problem_statement: str
    repo_context: Dict[str, Any]
    
    # Execution
    conversation: List[Dict[str, str]]  # messages
    tool_calls: List[Dict[str, Any]]
    code_changes: List[Dict[str, str]]
    
    # Outcome
    success: bool
    tests_passed: List[str]
    tests_failed: List[str]
    execution_time: float
    
    # For GRPO
    prompt: str  # The input prompt
    completion: str  # The generated code
    reward: float  # Computed reward
```

### 2. Reward Calculator (`src/training/reward_calculator.py`)

Computes multi-component rewards for training.

```python
from training.reward_calculator import RewardCalculator, RewardComponents

calculator = RewardCalculator(
    weights=RewardComponents(
        test_pass=0.5,
        code_quality=0.2,
        syntax_valid=0.1,
        execution_success=0.2
    )
)

reward = calculator.calculate(
    trace=execution_trace,
    test_results=test_results,
    static_analysis=lint_results
)
```

#### Reward Components

**Primary Rewards (Execution-Based)**
- `test_pass_reward`: Fraction of FAIL_TO_PASS tests passing
- `regression_penalty`: Penalty for PASS_TO_PASS failures
- `execution_success`: Code runs without errors

**Secondary Rewards (Quality-Based)**
- `syntax_valid`: Code parses correctly
- `lint_score`: Static analysis score (pylint, ruff)
- `complexity_penalty`: Penalize overly complex solutions

**Shaped Rewards (Process-Based)**
- `iteration_efficiency`: Fewer iterations = higher reward
- `tool_efficiency`: Efficient tool usage patterns
- `time_efficiency`: Faster resolution

#### Reward Formula

```
total_reward = (
    w1 * test_pass_reward +
    w2 * regression_penalty +
    w3 * syntax_valid +
    w4 * lint_score +
    w5 * iteration_efficiency +
    w6 * time_efficiency
)

Where w1 + w2 + w3 + w4 + w5 + w6 = 1.0
```

### 3. GRPO Trainer Integration (`src/training/grpo_trainer.py`)

Wraps TRL's GRPO trainer for AutoDev-specific training.

```python
from training.grpo_trainer import AutoDevGRPOTrainer, GRPOConfig

config = GRPOConfig(
    base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
    output_dir="~/.autodev/models/grpo_finetuned",
    
    # GRPO specific
    num_generations=4,  # K samples per prompt
    temperature=0.7,
    kl_coefficient=0.1,
    
    # Training
    learning_rate=1e-5,
    batch_size=8,
    num_epochs=3,
    
    # AutoDev specific
    reward_weights=RewardComponents(...)
)

trainer = AutoDevGRPOTrainer(config)
await trainer.train(
    training_data=traces,
    eval_data=eval_traces
)
```

#### GRPO Algorithm (TRL Integration)

```python
# Pseudocode for GRPO integration
class AutoDevGRPOTrainer:
    def train_step(self, batch):
        """
        For each prompt in batch:
        1. Generate K completions using current policy
        2. Compute rewards for each completion
        3. Compute relative advantages: A_i = (r_i - mean) / std
        4. Update policy: L = -E[A_i * log(π(y_i|x))] + β * KL
        """
        prompts = batch["prompts"]
        
        # Generate K samples per prompt
        completions = self.generate_samples(prompts, k=self.config.num_generations)
        
        # Compute rewards using RewardCalculator
        rewards = self.compute_rewards(prompts, completions)
        
        # Normalize within groups
        advantages = self.normalize_rewards(rewards)
        
        # GRPO loss
        loss = self.compute_grpo_loss(prompts, completions, advantages)
        
        # Backward pass
        loss.backward()
        self.optimizer.step()
```

### 4. Model Registry (`src/training/model_registry.py`)

Manages model versions and checkpoints.

```python
from training.model_registry import ModelRegistry

registry = ModelRegistry(
    storage_dir="~/.autodev/models",
    max_versions=10
)

# Register new model
registry.register(
    model_path="~/.autodev/models/grpo_finetuned_v1",
    metadata={
        "base_model": "Qwen/Qwen2.5-Coder-7B",
        "training_episodes": 1000,
        "avg_reward": 0.65,
        "swebench_rate": 0.23
    }
)

# List available models
models = registry.list_models()

# Load best model
best = registry.get_best_model(metric="swebench_rate")
```

### 5. Training Pipeline (`src/training/pipeline.py`)

Orchestrates the complete training workflow.

```python
from training.pipeline import TrainingPipeline, TrainingConfig

config = TrainingConfig(
    # Data collection
    num_swebench_tasks=100,
    subset="lite",
    
    # Training
    base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
    grpo_config=GRPOConfig(...),
    
    # Evaluation
    eval_interval=100,
    eval_tasks=20,
    
    # Continuous learning
    enable_continuous=True,
    min_episodes_for_training=50
)

pipeline = TrainingPipeline(config)
await pipeline.run()
```

---

## Integration Points

### 1. SWE-bench Harness Integration

Modify `swe_bench_harness.py` to capture training data:

```python
class SWEBenchHarness:
    def __init__(self, ..., training_collector=None):
        self.training_collector = training_collector
    
    async def run_task(self, task, task_workspace):
        result = await self._execute_task(task, task_workspace)
        
        # Capture training data
        if self.training_collector:
            await self.training_collector.capture_trace(
                task=task,
                result=result,
                workspace=task_workspace
            )
        
        return result
```

### 2. AutoDevPipeline Integration

Add hooks for training data capture:

```python
class AutoDevPipeline:
    def __init__(self, ..., trace_capture=False):
        self.trace_capture = trace_capture
        self._current_trace = None
    
    async def execute_task(self, task, ...):
        if self.trace_capture:
            self._current_trace = ExecutionTrace(...)
        
        # ... existing execution ...
        
        if self.trace_capture:
            self._current_trace.record_step(
                messages=messages,
                tool_calls=tool_calls,
                result=content
            )
```

### 3. LLM Client Integration

Support for fine-tuned models:

```python
class LLMClient:
    def __init__(self, config: LLMConfig):
        # Support for local fine-tuned models
        if config.model_path:
            self._load_local_model(config.model_path)
        else:
            self._setup_api_client(config.model)
    
    def _load_local_model(self, model_path):
        """Load a fine-tuned model for inference."""
        from transformers import AutoModelForCausalLM, AutoTokenizer
        
        self.model = AutoModelForCausalLM.from_pretrained(model_path)
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
```

---

## Directory Structure

```
src/training/
├── __init__.py
├── data_collector.py      # Training data collection
├── reward_calculator.py   # Reward computation
├── grpo_trainer.py        # TRL GRPO integration
├── model_registry.py      # Model version management
├── pipeline.py            # Training orchestration
├── config.py              # Training configurations
└── utils.py               # Helper functions

src/training/tests/
├── test_data_collector.py
├── test_reward_calculator.py
├── test_grpo_trainer.py
├── test_model_registry.py
└── test_pipeline.py

config/training/
├── grpo_config.yaml       # Default GRPO configuration
├── reward_weights.yaml    # Default reward weights
└── training_pipeline.yaml # Pipeline configuration

scripts/
├── collect_training_data.py   # CLI for data collection
├── train_grpo.py              # CLI for training
├── evaluate_model.py          # CLI for evaluation
└── export_model.py            # Export for deployment
```

---

## Implementation Phases

### Week 1-2: Training Data Infrastructure

**Deliverables:**
- [ ] `ExecutionTrace` data structure
- [ ] `TrainingDataCollector` implementation
- [ ] Integration with SWE-bench harness
- [ ] Data storage format (parquet)
- [ ] CLI for data collection

**Acceptance Criteria:**
- Collect 100+ execution traces from SWE-bench Lite
- Traces stored in efficient format
- Data includes all required fields for GRPO

### Week 2-3: Reward Calculator

**Deliverables:**
- [ ] Multi-component reward system
- [ ] Test-based rewards (FAIL_TO_PASS, PASS_TO_PASS)
- [ ] Quality-based rewards (lint, syntax)
- [ ] Efficiency rewards (iterations, time)
- [ ] Unit tests for all reward components

**Acceptance Criteria:**
- Rewards computed for all traces
- Reward distribution is well-calibrated
- Rewards correlate with resolution success

### Week 3-4: GRPO Trainer Integration

**Deliverables:**
- [ ] TRL GRPO trainer wrapper
- [ ] Custom reward function integration
- [ ] Training loop implementation
- [ ] Checkpointing and resume support
- [ ] Evaluation during training

**Acceptance Criteria:**
- Training runs successfully on collected data
- Loss decreases over training
- Model generates valid code

### Week 4-5: Model Registry & Deployment

**Deliverables:**
- [ ] Model version management
- [ ] Metadata tracking (metrics, training params)
- [ ] Best model selection
- [ ] Export for inference
- [ ] Integration with LLM client

**Acceptance Criteria:**
- Models versioned and tracked
- Can load fine-tuned model for inference
- Model comparison metrics available

### Week 5-6: Training Pipeline & Evaluation

**Deliverables:**
- [ ] End-to-end training pipeline
- [ ] Continuous learning support
- [ ] Evaluation on held-out SWE-bench tasks
- [ ] Performance comparison vs baseline

**Acceptance Criteria:**
- Full pipeline runs automatically
- Fine-tuned model improves on baseline
- 5%+ improvement on SWE-bench rate

---

## Dependencies

### Python Packages

```toml
[project.dependencies]
# Existing dependencies...
datasets = ">=2.14.0"
transformers = ">=4.36.0"
torch = ">=2.1.0"
accelerate = ">=0.25.0"

# New for Phase 8
trl = ">=0.8.0"           # GRPO trainer
peft = ">=0.7.0"          # LoRA for efficient fine-tuning
bitsandbytes = ">=0.41.0" # Quantization
pyarrow = ">=14.0.0"      # Parquet storage
wandb = ">=0.16.0"        # Experiment tracking (optional)
```

### Hardware Requirements

| Training Scale | GPU Memory | Training Time |
|----------------|------------|---------------|
| Prototype (7B) | 24GB | 2-4 hours |
| Production (7B) | 40GB+ | 8-16 hours |
| Large (14B+) | 80GB+ | 24+ hours |

**Recommended:**
- NVIDIA A100 40GB or equivalent
- 128GB+ system RAM
- 500GB+ SSD storage

---

## Configuration

### GRPO Configuration (`config/training/grpo_config.yaml`)

```yaml
model:
  base_model: "Qwen/Qwen2.5-Coder-7B-Instruct"
  use_peft: true
  lora_r: 16
  lora_alpha: 32
  lora_dropout: 0.05

grpo:
  num_generations: 4
  temperature: 0.7
  top_p: 0.9
  kl_coefficient: 0.1
  clip_range: 0.2

training:
  learning_rate: 1.0e-5
  batch_size: 8
  gradient_accumulation_steps: 4
  num_epochs: 3
  warmup_ratio: 0.1
  weight_decay: 0.01

evaluation:
  eval_interval: 100
  eval_steps: 50
  save_steps: 100
  load_best_model_at_end: true
```

### Reward Weights (`config/training/reward_weights.yaml`)

```yaml
primary:
  test_pass: 0.40
  regression_penalty: 0.15
  execution_success: 0.15

secondary:
  syntax_valid: 0.10
  lint_score: 0.10

efficiency:
  iteration_efficiency: 0.05
  time_efficiency: 0.05

total: 1.0  # Must sum to 1.0
```

---

## Usage Examples

### Collect Training Data

```bash
# Collect traces from SWE-bench Lite
python scripts/collect_training_data.py \
    --subset lite \
    --num-tasks 100 \
    --output ~/.autodev/training_data/traces_v1.parquet

# Collect with specific task IDs
python scripts/collect_training_data.py \
    --task-ids django__django-12345 flask__flask-67890 \
    --output traces_selected.parquet
```

### Train Model with GRPO

```bash
# Basic training
python scripts/train_grpo.py \
    --training-data ~/.autodev/training_data/traces_v1.parquet \
    --config config/training/grpo_config.yaml \
    --output ~/.autodev/models/grpo_v1

# Training with evaluation
python scripts/train_grpo.py \
    --training-data traces.parquet \
    --eval-data eval_traces.parquet \
    --eval-interval 100 \
    --output ~/.autodev/models/grpo_v2
```

### Evaluate Trained Model

```bash
# Evaluate on SWE-bench
python scripts/evaluate_model.py \
    --model ~/.autodev/models/grpo_v1 \
    --benchmark swebench_lite \
    --num-tasks 50 \
    --output evaluation_results.json

# Compare with baseline
python scripts/evaluate_model.py \
    --model ~/.autodev/models/grpo_v1 \
    --baseline Qwen/Qwen2.5-Coder-7B-Instruct \
    --num-tasks 50
```

### Use Fine-tuned Model

```python
from integration import AutoDevPipeline, PipelineConfig
from llm.client import LLMConfig

# Use fine-tuned local model
config = PipelineConfig(
    llm_config=LLMConfig(
        model_path="~/.autodev/models/grpo_v1",
        use_local=True
    )
)

async with AutoDevPipeline(config) as pipeline:
    result = await pipeline.execute_task("Fix the bug in utils.py")
```

---

## Evaluation Methodology

### Metrics

1. **Primary: SWE-bench Resolution Rate**
   - Compare baseline vs fine-tuned model
   - Target: +5% absolute improvement

2. **Secondary Metrics**
   - Test pass rate (FAIL_TO_PASS)
   - Regression rate (PASS_TO_PASS failures)
   - Code quality scores
   - Execution success rate

3. **Training Metrics**
   - Reward distribution over time
   - KL divergence from reference
   - Loss curves

### Evaluation Protocol

```python
async def evaluate_model(model_path, baseline_path, num_tasks=50):
    """Compare fine-tuned model against baseline."""
    
    # Load both models
    ft_pipeline = AutoDevPipeline(LLMConfig(model_path=model_path))
    base_pipeline = AutoDevPipeline(LLMConfig(model_path=baseline_path))
    
    # Load held-out tasks
    tasks = load_swebench_tasks(subset="lite", num_tasks=num_tasks, held_out=True)
    
    # Run evaluation
    ft_results = await evaluate_pipeline(ft_pipeline, tasks)
    base_results = await evaluate_pipeline(base_pipeline, tasks)
    
    # Compare
    comparison = {
        "baseline_resolution": base_results.resolution_rate,
        "finetuned_resolution": ft_results.resolution_rate,
        "improvement": ft_results.resolution_rate - base_results.resolution_rate,
        "statistical_significance": compute_p_value(base_results, ft_results)
    }
    
    return comparison
```

---

## Continuous Learning Loop

### Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Production     │     │  Training Data  │     │  GRPO Training  │
│  AutoDev        │────▶│  Collection     │────▶│  Pipeline       │
│  Pipeline       │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        ▲                                                │
        │                                                │
        └────────────────────────────────────────────────┘
                    Deploy Improved Model
```

### Implementation

```python
class ContinuousLearningLoop:
    def __init__(self, config):
        self.collector = TrainingDataCollector(...)
        self.trainer = AutoDevGRPOTrainer(...)
        self.registry = ModelRegistry(...)
        self.min_episodes = config.min_episodes_for_training
    
    async def run(self):
        while True:
            # Collect new episodes
            await self.collector.collect_episodes(num_episodes=100)
            
            # Check if enough data
            if self.collector.count() >= self.min_episodes:
                # Train
                new_model = await self.trainer.train(
                    self.collector.get_data()
                )
                
                # Evaluate
                if await self.is_better(new_model):
                    # Deploy
                    self.registry.register(new_model)
                    self.collector.clear()
            
            await asyncio.sleep(3600)  # Check hourly
```

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Reward hacking | Model exploits reward function | Multi-component rewards, regularization |
| Distribution shift | Real tasks differ from training | Diverse task sampling, continuous learning |
| Compute costs | Training expensive | LoRA/PEFT, gradient checkpointing |
| Mode collapse | Model generates similar outputs | KL penalty, temperature scheduling |
| Overfitting | Model memorizes training tasks | Hold-out evaluation, early stopping |

---

## Success Criteria

### Phase 8 Complete When:

- [ ] Training data collection operational (100+ traces)
- [ ] Reward calculator implemented with all components
- [ ] GRPO trainer integrated with TRL
- [ ] First fine-tuned model trained
- [ ] Model registry operational
- [ ] Evaluation shows improvement over baseline
- [ ] Documentation complete
- [ ] Tests passing with >80% coverage

### Stretch Goals:

- [ ] 25%+ SWE-bench resolution rate
- [ ] Continuous learning loop operational
- [ ] Multiple model versions with comparison
- [ ] Integration with experiment tracking (W&B)

---

## Future Enhancements (Post-Phase 8)

1. **Process Reward Models (PRM)**: Reward intermediate reasoning steps
2. **Multi-Modal Training**: Include diagrams, documentation
3. **Curriculum Learning**: Progressive difficulty
4. **Distributed Training**: Multi-GPU, multi-node
5. **Online Learning**: Real-time updates from production

---

## References

### Papers
- DeepSeek-V3 Technical Report: https://arxiv.org/abs/2412.19437
- Qwen2.5-Coder: https://arxiv.org/abs/2409.12186
- CodeRL: https://arxiv.org/abs/2207.01780
- TRL Documentation: https://huggingface.co/docs/trl

### Code
- TRL (Transformer Reinforcement Learning): https://github.com/huggingface/trl
- DeepSpeed-Chat: https://github.com/microsoft/DeepSpeed-Chat

### Internal
- Knowledge Graph: `~/Documents/Obsidian/Hermes/Knowledge/AutoDev/RL_GRPO_Code_Generation.md`
- Phase 7 Docs: `docs/phase7_swe_bench_harness.md`

---

*Last updated: 2026-03-23 (Phase 8 Planning - RL Training Integration)*
