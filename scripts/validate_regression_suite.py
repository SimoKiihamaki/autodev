#!/usr/bin/env python3
"""
Validation script for the performance regression test suite.

This script performs basic validation to ensure the test suite is properly configured
and can run successfully.
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
BASELINE_FILE = PROJECT_ROOT / "benchmarks" / "baselines" / "phase10.1.json"
REGRESSION_TASKS_FILE = PROJECT_ROOT / "autodev" / "config" / "regression_tasks.json"
TEST_FILE = PROJECT_ROOT / "tests" / "regression" / "test_performance.py"


def validate_files_exist():
    """Validate that all required files exist."""
    print("Validating file structure...")
    
    files_to_check = [
        ("Baseline metrics", BASELINE_FILE),
        ("Regression tasks config", REGRESSION_TASKS_FILE),
        ("Test suite", TEST_FILE),
    ]
    
    all_exist = True
    for name, filepath in files_to_check:
        if filepath.exists():
            print(f"  ✓ {name}: {filepath}")
        else:
            print(f"  ✗ {name} NOT FOUND: {filepath}")
            all_exist = False
    
    return all_exist


def validate_baseline_file():
    """Validate baseline metrics file structure."""
    print("\nValidating baseline metrics file...")
    
    try:
        with open(BASELINE_FILE, 'r') as f:
            baseline = json.load(f)
        
        # Check required sections
        required_sections = ['metadata', 'summary', 'latency', 'phase_timings', 'tasks']
        all_sections = True
        
        for section in required_sections:
            if section in baseline:
                print(f"  ✓ Section '{section}' found")
            else:
                print(f"  ✗ Section '{section}' missing")
                all_sections = False
        
        # Check tasks
        if 'tasks' in baseline:
            task_count = len(baseline['tasks'])
            print(f"  ✓ Found {task_count} baseline tasks")
            if task_count < 5:
                print(f"  ⚠ Expected at least 5 tasks")
        
        # Check latency metrics
        if 'latency' in baseline:
            avg_latency = baseline['latency'].get('avg_task_latency_seconds', 0)
            print(f"  ✓ Average latency: {avg_latency:.3f}s")
        
        return all_sections
        
    except Exception as e:
        print(f"  ✗ Error reading baseline file: {e}")
        return False


def validate_regression_tasks():
    """Validate regression tasks configuration."""
    print("\nValidating regression tasks configuration...")
    
    try:
        with open(REGRESSION_TASKS_FILE, 'r') as f:
            config = json.load(f)
        
        if 'tasks' not in config:
            print("  ✗ No 'tasks' section found")
            return False
        
        tasks = config['tasks']
        task_count = len(tasks)
        
        print(f"  ✓ Found {task_count} regression tasks")
        
        if task_count != 5:
            print(f"  ⚠ Expected exactly 5 tasks, found {task_count}")
        
        # Validate each task has required fields
        for i, task in enumerate(tasks):
            if 'instance_id' in task and 'repo' in task:
                print(f"  ✓ Task {i+1}: {task['instance_id']}")
            else:
                print(f"  ✗ Task {i+1} missing required fields")
                return False
        
        return True
        
    except Exception as e:
        print(f"  ✗ Error reading regression tasks file: {e}")
        return False


def validate_test_file():
    """Validate test file structure."""
    print("\nValidating test file...")
    
    try:
        with open(TEST_FILE, 'r') as f:
            content = f.read()
        
        # Check for key components
        checks = [
            ('HierarchicalExecutorWithMetrics', 'Executor class'),
            ('TestPerformanceRegression', 'Test class'),
            ('test_average_latency_regression', 'Average latency test'),
            ('test_individual_task_performance', 'Individual task test'),
            ('PERFORMANCE_THRESHOLD', 'Performance threshold constant'),
        ]
        
        all_found = True
        for marker, description in checks:
            if marker in content:
                print(f"  ✓ {description} found")
            else:
                print(f"  ✗ {description} NOT found")
                all_found = False
        
        return all_found
        
    except Exception as e:
        print(f"  ✗ Error reading test file: {e}")
        return False


def main():
    """Run all validations."""
    print("=" * 70)
    print("Performance Regression Test Suite Validation")
    print("=" * 70)
    
    results = []
    
    results.append(("File Structure", validate_files_exist()))
    results.append(("Baseline Metrics", validate_baseline_file()))
    results.append(("Regression Tasks", validate_regression_tasks()))
    results.append(("Test File", validate_test_file()))
    
    print("\n" + "=" * 70)
    print("Validation Summary")
    print("=" * 70)
    
    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")
        if not passed:
            all_passed = False
    
    print("=" * 70)
    
    if all_passed:
        print("\n✅ All validations passed!")
        print("\nNext steps:")
        print("  1. Run tests: pytest tests/regression/test_performance.py -v")
        print("  2. Review results and adjust thresholds if needed")
        print("  3. Integrate into CI/CD pipeline")
        return 0
    else:
        print("\n❌ Some validations failed. Please fix issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
