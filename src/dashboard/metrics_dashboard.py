"""
AutoDev Metrics Dashboard - Rich-based TUI for Training Pipeline Monitoring

This module provides a real-time terminal dashboard for monitoring the AutoDev
training pipeline, including data collection, GRPO training, and evaluation.

Usage:
    from dashboard.metrics_dashboard import MetricsDashboard
    from training.orchestrator import TrainingOrchestrator

    dashboard = MetricsDashboard()
    orchestrator = TrainingOrchestrator(config)
    orchestrator.add_progress_callback(dashboard.update)

    # Start live display
    with dashboard:
        await orchestrator.run_training_cycle(...)

Integration:
    The dashboard.update() method accepts ProgressInfo directly from the
    TrainingOrchestrator's progress callbacks.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from rich.console import Console, RenderableType
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from training.orchestrator import ProgressInfo, OrchestratorStage


@dataclass
class DashboardMetrics:
    """Container for all dashboard metrics (mirrors ProgressInfo)."""
    stage: str = "idle"
    stage_progress: float = 0.0
    total_episodes: int = 0
    completed_episodes: int = 0
    total_steps: int = 0
    completed_steps: int = 0
    current_epoch: int = 0
    traces_collected: int = 0
    traces_processed: int = 0
    evaluations_completed: int = 0
    best_resolution_rate: float = 0.0
    elapsed_time: float = 0.0
    estimated_remaining: float = 0.0

    # Evaluation metrics (extended beyond ProgressInfo)
    resolved_tasks: int = 0
    total_eval_tasks: int = 0
    failed_tasks: int = 0
    timeout_count: int = 0  # Separate timeout tracking
    avg_execution_time: float = 0.0  # Average execution time in seconds
    eval_cost: float = 0.0
    tokens_used: int = 0

    # Comparison metrics (from ComparisonResult)
    tasks_improved: int = 0
    tasks_regressed: int = 0
    improvement_percent: float = 0.0


class MetricsDashboard:
    """
    Rich-based TUI dashboard for monitoring AutoDev training pipeline.

    Provides a 3-panel layout:
    - Header: Pipeline status and overall progress
    - Metrics: Split view of training and evaluation metrics
    - Progress: Progress bars and timing information

    Attributes:
        refresh_rate: How often to refresh the display (Hz)
        console: Rich console for rendering
        metrics: Current metrics state
    """

    def __init__(self, refresh_rate: float = 4.0):
        """
        Initialize the Metrics Dashboard.

        Args:
            refresh_rate: Display refresh rate in Hz (default: 4)
        """
        self.refresh_rate = refresh_rate
        self.console = Console()
        self.metrics = DashboardMetrics()
        self._live: Optional[Live] = None
        self._layout = self._build_layout()

    def _build_layout(self) -> Layout:
        """Construct the 3-panel layout structure."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="metrics", ratio=2),
            Layout(name="progress", size=5),
        )

        # Split metrics into training/evaluation columns
        layout["metrics"].split_row(
            Layout(name="training", ratio=1),
            Layout(name="evaluation", ratio=1),
        )

        return layout

    def _render_header(self) -> Panel:
        """Render the header panel with status and overall progress."""
        stage = self.metrics.stage.upper()
        progress_pct = self.metrics.stage_progress * 100

        # Status indicator color
        status_colors = {
            "idle": "dim",
            "initializing": "yellow",
            "collecting_data": "cyan",
            "training": "green",
            "evaluating": "magenta",
            "completed": "bold green",
            "failed": "bold red",
            "cancelled": "bold yellow",
        }
        color = status_colors.get(stage.lower(), "white")

        title = Text.assemble(
            "AutoDev Pipeline  ",
            (f"[{stage}]", color),
            f"  {progress_pct:.1f}%",
        )

        return Panel(title, style="bold blue", padding=(0, 1))

    def _render_training_metrics(self) -> Panel:
        """Render training metrics panel."""
        table = Table(show_header=False, box=None, expand=True, padding=(0, 1))
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white", justify="right")

        table.add_row("Traces Collected", f"{self.metrics.traces_collected}")
        table.add_row("Traces Processed", f"{self.metrics.traces_processed}")
        table.add_row("Epoch", f"{self.metrics.current_epoch}")
        table.add_row("Episodes", f"{self.metrics.completed_episodes}/{self.metrics.total_episodes}")
        table.add_row("Best Rate", f"{self.metrics.best_resolution_rate:.1%}")

        return Panel(table, title="TRAINING", border_style="cyan", padding=(0, 1))

    def _render_evaluation_metrics(self) -> Panel:
        """Render evaluation metrics panel."""
        table = Table(show_header=False, box=None, expand=True, padding=(0, 1))
        table.add_column("Metric", style="magenta")
        table.add_column("Value", style="white", justify="right")

        if self.metrics.total_eval_tasks > 0:
            res_pct = self.metrics.resolved_tasks / self.metrics.total_eval_tasks * 100
            res_str = f"{self.metrics.resolved_tasks}/{self.metrics.total_eval_tasks} ({res_pct:.0f}%)"
        else:
            res_str = "—"

        table.add_row("Resolved", res_str)
        table.add_row("Failed", f"{self.metrics.failed_tasks}")
        table.add_row("Timeouts", f"{self.metrics.timeout_count}")
        table.add_row("Avg Time", f"{self.metrics.avg_execution_time:.0f}s" if self.metrics.avg_execution_time > 0 else "—")
        table.add_row("Cost", f"${self.metrics.eval_cost:.2f}")
        table.add_row("Tokens", f"{self.metrics.tokens_used/1e6:.1f}M" if self.metrics.tokens_used else "—")

        # Add comparison metrics if available
        if self.metrics.tasks_improved > 0 or self.metrics.tasks_regressed > 0:
            table.add_row("")  # Separator
            improved_color = "green" if self.metrics.improvement_percent > 0 else "red"
            table.add_row(
                "Improved",
                f"[{improved_color}]+{self.metrics.tasks_improved}[/{improved_color}]"
            )
            table.add_row(
                "Regressed",
                f"[red]-{self.metrics.tasks_regressed}[/red]"
            )
            table.add_row(
                "Change",
                f"[{improved_color}]{self.metrics.improvement_percent:+.1f}%[/{improved_color}]"
            )

        return Panel(table, title="EVALUATION", border_style="magenta", padding=(0, 1))

    def _render_progress(self) -> Panel:
        """Render progress panel with bars and timing."""
        progress = Progress(
            TextColumn("[bold blue]{task.description}", justify="left"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})", justify="right"),
            TimeElapsedColumn(),
            expand=True,
        )

        # Main progress bar
        if self.metrics.total_steps > 0:
            progress.add_task(
                "[cyan]Steps",
                total=self.metrics.total_steps,
                completed=self.metrics.completed_steps,
            )
        else:
            progress.add_task("[cyan]Steps", total=100, completed=0)

        # Timing row
        elapsed = self._format_time(self.metrics.elapsed_time)
        eta = self._format_time(self.metrics.estimated_remaining)

        timing_text = Text.assemble(
            "Elapsed: ", (elapsed, "green"),
            "   ETA: ", (eta if self.metrics.estimated_remaining > 0 else "—", "yellow"),
        )

        # Combine progress and timing
        from rich.console import Group
        content = Group(progress, timing_text)

        return Panel(content, title="PROGRESS", border_style="blue", padding=(0, 1))

    def _format_time(self, seconds: float) -> str:
        """Format seconds into HH:MM:SS string."""
        if seconds <= 0:
            return "—"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _render(self) -> RenderableType:
        """Render the complete dashboard layout."""
        self._layout["header"].update(self._render_header())
        self._layout["training"].update(self._render_training_metrics())
        self._layout["evaluation"].update(self._render_evaluation_metrics())
        self._layout["progress"].update(self._render_progress())
        return self._layout

    # -------------------------------------------------------------------------
    # Public API - Progress Callback Interface
    # -------------------------------------------------------------------------

    def update(self, progress_info: "ProgressInfo") -> None:
        """
        Update dashboard metrics from TrainingOrchestrator progress callback.

        This method is designed to be registered as a callback with the
        TrainingOrchestrator's add_progress_callback() method.

        Args:
            progress_info: ProgressInfo instance from the orchestrator
        """
        # Handle both dataclass and dict inputs
        if hasattr(progress_info, "stage"):
            self.metrics.stage = progress_info.stage.value if hasattr(progress_info.stage, "value") else str(progress_info.stage)
            self.metrics.stage_progress = progress_info.stage_progress
            self.metrics.total_episodes = progress_info.total_episodes
            self.metrics.completed_episodes = progress_info.completed_episodes
            self.metrics.total_steps = progress_info.total_steps
            self.metrics.completed_steps = progress_info.completed_steps
            self.metrics.current_epoch = progress_info.current_epoch
            self.metrics.traces_collected = progress_info.traces_collected
            self.metrics.traces_processed = progress_info.traces_processed
            self.metrics.evaluations_completed = progress_info.evaluations_completed
            self.metrics.best_resolution_rate = progress_info.best_resolution_rate
            self.metrics.elapsed_time = progress_info.elapsed_time
            self.metrics.estimated_remaining = progress_info.estimated_remaining
        else:
            # Dict input
            self.metrics.stage = progress_info.get("stage", "idle")
            self.metrics.stage_progress = progress_info.get("stage_progress", 0.0)
            self.metrics.total_steps = progress_info.get("total_steps", 0)
            self.metrics.completed_steps = progress_info.get("completed_steps", 0)
            self.metrics.traces_collected = progress_info.get("traces_collected", 0)
            self.metrics.elapsed_time = progress_info.get("elapsed_time", 0.0)

    def update_evaluation(self, resolved: int, total: int, failed: int = 0,
                          cost: float = 0.0, tokens: int = 0,
                          timeouts: int = 0, avg_execution_time: float = 0.0) -> None:
        """
        Update evaluation-specific metrics.

        Args:
            resolved: Number of resolved tasks
            total: Total evaluation tasks
            failed: Number of failed tasks
            cost: Total evaluation cost
            tokens: Total tokens used
            timeouts: Number of timed out tasks
            avg_execution_time: Average execution time in seconds
        """
        self.metrics.resolved_tasks = resolved
        self.metrics.total_eval_tasks = total
        self.metrics.failed_tasks = failed
        self.metrics.timeout_count = timeouts
        self.metrics.avg_execution_time = avg_execution_time
        self.metrics.eval_cost = cost
        self.metrics.tokens_used = tokens

    def update_comparison(self, comparison_result) -> None:
        """
        Update comparison metrics from ComparisonResult.

        Accepts ComparisonResult from swebench_runner.py and extracts
        tasks_improved, tasks_regressed, and improvement_percent for display.

        Args:
            comparison_result: ComparisonResult instance from swebench_runner,
                             or a dict with 'tasks_improved', 'tasks_regressed',
                             and 'improvement_percent' keys
        """
        if hasattr(comparison_result, "tasks_improved"):
            # ComparisonResult dataclass input
            self.metrics.tasks_improved = len(comparison_result.tasks_improved)
            self.metrics.tasks_regressed = len(comparison_result.tasks_regressed)
            self.metrics.improvement_percent = comparison_result.improvement_percent
        else:
            # Dict input
            tasks_improved = comparison_result.get("tasks_improved", [])
            tasks_regressed = comparison_result.get("tasks_regressed", [])
            self.metrics.tasks_improved = len(tasks_improved) if isinstance(tasks_improved, list) else tasks_improved
            self.metrics.tasks_regressed = len(tasks_regressed) if isinstance(tasks_regressed, list) else tasks_regressed
            self.metrics.improvement_percent = comparison_result.get("improvement_percent", 0.0)

    # -------------------------------------------------------------------------
    # Context Manager Interface
    # -------------------------------------------------------------------------

    def __enter__(self) -> "MetricsDashboard":
        """Start the live display."""
        self._live = Live(
            self._render(),
            console=self.console,
            refresh_per_second=self.refresh_rate,
            screen=False,  # Allow scrolling in terminal
        )
        self._live.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Stop the live display."""
        if self._live:
            self._live.__exit__(exc_type, exc_val, exc_tb)
            self._live = None

    def start(self) -> None:
        """Start the live display (non-context manager mode)."""
        if not self._live:
            self._live = Live(
                self._render(),
                console=self.console,
                refresh_per_second=self.refresh_rate,
                screen=False,
            )
            self._live.start()

    def stop(self) -> None:
        """Stop the live display (non-context manager mode)."""
        if self._live:
            self._live.stop()
            self._live = None

    def refresh(self) -> None:
        """Force a display refresh."""
        if self._live:
            self._live.update(self._render())


# Convenience function for quick dashboard creation
def create_dashboard() -> MetricsDashboard:
    """Create a new MetricsDashboard instance with default settings."""
    return MetricsDashboard()
