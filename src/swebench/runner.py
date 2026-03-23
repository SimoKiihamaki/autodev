"""
SWE-bench Runner Module

Provides a programmatic API for running SWE-bench Lite validation
and integrating with AutoDev's solver pipeline.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class InstanceResult:
    """Result from running a single SWE-bench instance"""
    instance_id: str
    resolved: bool
    patch: Optional[str]
    error: Optional[str]
    metrics: Dict


class SWEbenchRunner:
    """
    Runner for SWE-bench Lite validation.
    
    This class provides a high-level API for running SWE-bench benchmarks
    and can be integrated into CI/CD pipelines or development workflows.
    
    Example:
        >>> runner = SWEbenchRunner()
        >>> runner.set_solver(my_custom_solver)
        >>> metrics = runner.run_benchmark(subset_size=50)
        >>> print(f"Resolution rate: {metrics['resolution_rate']:.2%}")
    """
    
    def __init__(self, output_dir: str = "results"):
        """
        Initialize SWE-bench runner.
        
        Args:
            output_dir: Directory to store results and logs
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.solver: Optional[Callable] = None
        
    def set_solver(self, solver: Callable[[Dict], Optional[str]]):
        """
        Set the solver function for generating patches.
        
        Args:
            solver: Function that takes an instance dict and returns a patch string
            
        Example:
            >>> def my_solver(instance):
            ...     # Analyze problem and generate patch
            ...     return "diff --git a/file.py..."
            >>> runner.set_solver(my_solver)
        """
        self.solver = solver
        logger.info("Solver function configured")
    
    def run_single_instance(
        self, 
        instance: Dict,
        timeout: int = 600
    ) -> InstanceResult:
        """
        Run a single SWE-bench instance.
        
        Args:
            instance: SWE-bench instance dictionary
            timeout: Timeout in seconds
            
        Returns:
            InstanceResult with resolution status and metrics
        """
        instance_id = instance.get('instance_id', 'unknown')
        
        if not self.solver:
            logger.error("No solver configured. Call set_solver() first.")
            return InstanceResult(
                instance_id=instance_id,
                resolved=False,
                patch=None,
                error="No solver configured",
                metrics={}
            )
        
        try:
            # Generate patch using configured solver
            logger.info(f"Running solver for instance: {instance_id}")
            patch = self.solver(instance)
            
            if not patch:
                logger.warning(f"Solver returned no patch for {instance_id}")
                return InstanceResult(
                    instance_id=instance_id,
                    resolved=False,
                    patch=None,
                    error="No patch generated",
                    metrics={'solver_status': 'no_patch'}
                )
            
            # TODO: Apply patch and run tests
            # This is a placeholder for the actual evaluation logic
            resolved = False  # Will be determined by test results
            
            logger.info(f"Patch generated for {instance_id}, length: {len(patch)}")
            
            return InstanceResult(
                instance_id=instance_id,
                resolved=resolved,
                patch=patch,
                error=None,
                metrics={
                    'patch_length': len(patch),
                    'repo': instance.get('repo', 'unknown')
                }
            )
            
        except Exception as e:
            logger.error(f"Error processing {instance_id}: {e}")
            return InstanceResult(
                instance_id=instance_id,
                resolved=False,
                patch=None,
                error=str(e),
                metrics={'exception': str(e)}
            )
    
    def run_benchmark(
        self,
        subset_size: Optional[int] = None,
        timeout: int = 600
    ) -> Dict:
        """
        Run the SWE-bench Lite benchmark.
        
        Args:
            subset_size: Number of instances to run (None for all)
            timeout: Timeout per instance in seconds
            
        Returns:
            Dictionary with metrics and results
        """
        logger.info("Starting SWE-bench Lite benchmark run")
        
        # Load dataset
        try:
            from datasets import load_dataset
            dataset = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
            instances = list(dataset)
            
            if subset_size:
                instances = instances[:subset_size]
                
            logger.info(f"Loaded {len(instances)} instances")
            
        except ImportError:
            logger.error("datasets library not installed. Run: pip install datasets")
            return {
                'error': 'Missing dependencies',
                'resolution_rate': 0.0,
                'total_instances': 0
            }
        
        # Run each instance
        results: List[InstanceResult] = []
        resolved_count = 0
        
        for idx, instance in enumerate(instances, 1):
            logger.info(f"Processing instance {idx}/{len(instances)}")
            
            result = self.run_single_instance(instance, timeout)
            results.append(result)
            
            if result.resolved:
                resolved_count += 1
        
        # Calculate metrics
        total = len(instances)
        resolution_rate = resolved_count / total if total > 0 else 0.0
        
        metrics = {
            'total_instances': total,
            'resolved_count': resolved_count,
            'failed_count': total - resolved_count,
            'resolution_rate': resolution_rate,
            'target_met': resolution_rate >= 0.30,
            'timestamp': datetime.now().isoformat(),
            'results': [
                {
                    'instance_id': r.instance_id,
                    'resolved': r.resolved,
                    'error': r.error
                }
                for r in results
            ]
        }
        
        # Save results
        self._save_results(metrics)
        
        logger.info(f"Benchmark complete. Resolution rate: {resolution_rate:.2%}")
        return metrics
    
    def _save_results(self, metrics: Dict, filename: str = "runner_results.json"):
        """Save results to JSON file"""
        output_path = self.output_dir / filename
        with open(output_path, 'w') as f:
            json.dump(metrics, f, indent=2, default=str)
        
        logger.info(f"Results saved to {output_path}")
    
    @staticmethod
    def check_dependencies() -> Dict[str, bool]:
        """
        Check if required dependencies are installed.
        
        Returns:
            Dictionary with dependency status
        """
        deps = {}
        
        try:
            import datasets
            deps['datasets'] = True
        except ImportError:
            deps['datasets'] = False
        
        try:
            import swebench_metrics
            deps['swebench_metrics'] = True
        except ImportError:
            deps['swebench_metrics'] = False
        
        return deps
    
    @staticmethod
    def get_phase10_status(resolution_rate: float) -> Dict:
        """
        Get Phase 10 status based on resolution rate.
        
        Args:
            resolution_rate: Current resolution rate (0.0 to 1.0)
            
        Returns:
            Status dictionary
        """
        target = 0.30
        
        return {
            'current_rate': resolution_rate,
            'target_rate': target,
            'target_met': resolution_rate >= target,
            'gap': max(0, target - resolution_rate),
            'status': 'PASS' if resolution_rate >= target else 'FAIL',
            'message': f"{'✓' if resolution_rate >= target else '✗'} Target {'met' if resolution_rate >= target else 'not met'}"
        }


# Convenience function for quick validation
def quick_validation(subset_size: int = 10) -> Dict:
    """
    Run a quick validation with default settings.
    
    Args:
        subset_size: Number of instances to test
        
    Returns:
        Metrics dictionary
    """
    runner = SWEbenchRunner()
    
    # Use a dummy solver for testing
    def dummy_solver(instance):
        return None  # Placeholder
    
    runner.set_solver(dummy_solver)
    return runner.run_benchmark(subset_size=subset_size)
