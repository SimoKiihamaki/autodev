#!/usr/bin/env python3
"""
Example: AutoDev Integration with SWE-bench Lite

This script demonstrates how to integrate AutoDev's solver
with the SWE-bench validation runner.
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from swebench.runner import SWEbenchRunner


def autodev_solver(instance: dict) -> str:
    """
    Example solver function that integrates with AutoDev.
    
    This is a placeholder that shows the expected interface.
    In production, this would call AutoDev's actual solver.
    
    Args:
        instance: SWE-bench instance containing:
            - instance_id: Unique identifier
            - repo: Repository name (e.g., "django/django")
            - problem_statement: Description of the issue
            - base_commit: Starting commit hash
            - hints_text: Optional hints
            
    Returns:
        Git diff patch string or None if generation failed
    """
    instance_id = instance.get('instance_id', 'unknown')
    repo = instance.get('repo', 'unknown')
    problem = instance.get('problem_statement', '')
    
    print(f"\n{'='*70}")
    print(f"Solving: {instance_id}")
    print(f"Repository: {repo}")
    print(f"Problem: {problem[:200]}...")
    print('='*70)
    
    # TODO: Replace with actual AutoDev solver integration
    # Example integration:
    #
    # from autodev.solver import AutoDevSolver
    #
    # solver = AutoDevSolver(
    #     model="gpt-4",
    #     temperature=0.7,
    #     max_tokens=2000
    # )
    #
    # # Clone repo at base commit
    # repo_path = solver.clone_repo(
    #     repo=instance['repo'],
    #     commit=instance['base_commit']
    # )
    #
    # # Generate patch
    # patch = solver.generate_patch(
    #     repo_path=repo_path,
    #     problem_statement=instance['problem_statement'],
    #     hints=instance.get('hints_text')
    # )
    #
    # return patch
    
    # Placeholder: Return None to indicate no patch generated
    print("⚠ Placeholder solver - no actual patch generated")
    return None


def main():
    """Run SWE-bench Lite validation with AutoDev integration"""
    
    print("\n" + "="*70)
    print("SWE-bench Lite Validation with AutoDev")
    print("="*70)
    
    # Check dependencies
    deps = SWEbenchRunner.check_dependencies()
    print("\nDependency Status:")
    for dep, installed in deps.items():
        status = "✓" if installed else "✗"
        print(f"  {status} {dep}")
    
    if not deps.get('datasets'):
        print("\n❌ Missing required dependency: datasets")
        print("Install with: pip install datasets")
        return
    
    # Create runner
    runner = SWEbenchRunner(output_dir="results")
    
    # Configure solver
    runner.set_solver(autodev_solver)
    
    # Run benchmark
    print("\n🚀 Running benchmark (subset of 5 for demo)...")
    metrics = runner.run_benchmark(subset_size=5)
    
    # Display results
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)
    print(f"Total Instances: {metrics['total_instances']}")
    print(f"Resolved: {metrics['resolved_count']}")
    print(f"Resolution Rate: {metrics['resolution_rate']:.2%}")
    
    # Check Phase 10 status
    status = SWEbenchRunner.get_phase10_status(metrics['resolution_rate'])
    print(f"\nPhase 10 Status: {status['message']}")
    
    if not status['target_met']:
        print(f"Gap to target: {status['gap']:.2%}")
    
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    main()
