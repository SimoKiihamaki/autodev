#!/usr/bin/env python3
"""
SWE-bench Test Harness Runner

Easy-to-use script for running SWE-bench evaluations.

Usage:
    python run_swe_bench.py --num-tasks 5 --subset lite
    python run_swe_bench.py --task-ids django__django-12345
    python run_swe_bench.py --report-only results.json
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.swe_bench_harness import SWEBenchHarness, EvaluationResults
from benchmark.reporting import ResultsReporter


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("swe_bench_run.log")
        ]
    )
    
    # Reduce noise from libraries
    logging.getLogger("datasets").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


async def run_evaluation(args) -> EvaluationResults:
    """Run the SWE-bench evaluation."""
    harness = SWEBenchHarness(
        workspace=args.workspace,
        timeout_seconds=args.timeout,
        max_iterations=args.max_iterations,
        model=args.model
    )
    
    results = await harness.run_evaluation(
        subset=args.subset,
        num_tasks=args.num_tasks,
        task_ids=args.task_ids,
        parallel=args.parallel,
        max_parallel=args.max_parallel
    )
    
    return results


def generate_report(results: EvaluationResults, output_dir: Path):
    """Generate and save reports."""
    reporter = ResultsReporter(results.to_dict())
    
    # Save markdown report
    report_path = output_dir / "evaluation_report.md"
    reporter.save_report(report_path)
    print(f"\n📄 Report saved to: {report_path}")
    
    # Also save JSON
    json_path = output_dir / "evaluation_results.json"
    with open(json_path, "w") as f:
        json.dump(results.to_dict(), f, indent=2, default=str)
    print(f"📊 JSON results saved to: {json_path}")


def print_summary(results: EvaluationResults):
    """Print evaluation summary to console."""
    print("\n" + "=" * 60)
    print("📊 SWE-bench Evaluation Results")
    print("=" * 60)
    print(f"\nTotal Tasks:     {results.total_tasks}")
    print(f"Resolved:        {results.resolved}")
    print(f"Failed:          {results.failed}")
    print(f"Errors:          {results.errors}")
    print(f"Timeouts:        {results.timeouts}")
    
    print(f"\n{'─' * 40}")
    status = "✅ PASSED" if results.resolution_rate >= 0.20 else "❌ BELOW TARGET"
    print(f"Resolution Rate: {results.resolution_rate:.1%}")
    print(f"Target:          20%+")
    print(f"Status:          {status}")
    print(f"{'─' * 40}")
    
    print(f"\n⏱️  Avg Execution Time: {results.avg_execution_time:.1f}s")
    print(f"💰 Total Cost:         ${results.total_cost_estimate:.2f}")
    print(f"📝 Total Tokens:       {results.total_tokens['total_tokens']:,}")
    
    if results.patterns.get("common_success_tools"):
        print("\n🔧 Most Used Tools (Success):")
        for tool, count in list(results.patterns["common_success_tools"].items())[:5]:
            print(f"   - {tool}: {count}")
    
    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="SWE-bench Test Harness for AutoDev",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run 10 tasks from SWE-bench Lite
  python run_swe_bench.py --num-tasks 10 --subset lite
  
  # Run specific tasks
  python run_swe_bench.py --task-ids django__django-12345 flask-admin__flask-admin-67890
  
  # Run with parallel execution
  python run_swe_bench.py --num-tasks 20 --parallel --max-parallel 5
  
  # Use Claude 3.5 Sonnet
  python run_swe_bench.py --num-tasks 10 --model claude-3-5-sonnet-20241022
"""
    )
    
    # Evaluation parameters
    parser.add_argument("--num-tasks", type=int, default=10,
                        help="Number of tasks to evaluate (default: 10)")
    parser.add_argument("--subset", choices=["lite", "full", "verified"],
                        default="lite", help="Dataset subset (default: lite)")
    parser.add_argument("--task-ids", nargs="+",
                        help="Specific task IDs to evaluate")
    
    # Execution parameters
    parser.add_argument("--workspace", default="/tmp/swebench_workspace",
                        help="Workspace directory (default: /tmp/swebench_workspace)")
    parser.add_argument("--timeout", type=int, default=1800,
                        help="Timeout per task in seconds (default: 1800)")
    parser.add_argument("--max-iterations", type=int, default=30,
                        help="Max tool iterations per task (default: 30)")
    parser.add_argument("--parallel", action="store_true",
                        help="Run tasks in parallel")
    parser.add_argument("--max-parallel", type=int, default=3,
                        help="Max parallel tasks (default: 3)")
    
    # Model configuration
    parser.add_argument("--model", default="claude-3-5-sonnet-20241022",
                        help="LLM model to use")
    
    # Output options
    parser.add_argument("--output-dir", type=str,
                        help="Output directory for reports")
    parser.add_argument("--report-only", type=str,
                        help="Generate report from existing results file")
    
    # Debug options
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable verbose logging")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show configuration without running")
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    # Check API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("❌ Error: ANTHROPIC_API_KEY environment variable not set")
        print("   Set it with: export ANTHROPIC_API_KEY='your-key'")
        sys.exit(1)
    
    # Determine output directory
    output_dir = Path(args.output_dir) if args.output_dir else Path(args.workspace) / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Report only mode
    if args.report_only:
        with open(args.report_only) as f:
            data = json.load(f)
        results = EvaluationResults(
            total_tasks=data["total_tasks"],
            resolved=data["resolved"],
            failed=data["failed"],
            errors=data["errors"],
            timeouts=data["timeouts"],
            resolution_rate=data["resolution_rate"],
            avg_execution_time=data["avg_execution_time"],
            total_tokens=data["total_tokens"],
            total_cost_estimate=data["total_cost_estimate"],
            task_results=[],  # Simplified
            patterns=data["patterns"],
            timestamp=data["timestamp"]
        )
        generate_report(results, output_dir)
        return
    
    # Dry run mode
    if args.dry_run:
        print("🔍 Dry Run - Configuration:")
        print(f"   Subset:         {args.subset}")
        print(f"   Num Tasks:      {args.num_tasks}")
        print(f"   Task IDs:       {args.task_ids}")
        print(f"   Workspace:      {args.workspace}")
        print(f"   Timeout:        {args.timeout}s")
        print(f"   Max Iterations: {args.max_iterations}")
        print(f"   Model:          {args.model}")
        print(f"   Parallel:       {args.parallel}")
        print(f"   Output Dir:     {output_dir}")
        return
    
    # Run evaluation
    print(f"\n🚀 Starting SWE-bench evaluation...")
    print(f"   Subset: {args.subset}")
    print(f"   Tasks:  {args.num_tasks if not args.task_ids else len(args.task_ids)}")
    print(f"   Model:  {args.model}")
    
    start_time = datetime.utcnow()
    
    try:
        results = asyncio.run(run_evaluation(args))
        
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        print(f"\n⏰ Total evaluation time: {duration:.1f}s")
        
        # Print summary
        print_summary(results)
        
        # Generate reports
        generate_report(results, output_dir)
        
        # Exit with appropriate code
        if results.resolution_rate >= 0.20:
            sys.exit(0)  # Success
        else:
            sys.exit(1)  # Below target
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Evaluation interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Evaluation failed: {e}")
        print(f"\n❌ Evaluation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
