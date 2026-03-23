"""
SWE-bench Reporting Module

Provides functionality for generating reports and analyzing results.
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ReportSection:
    """A section in the report."""
    title: str
    content: str
    subsections: List["ReportSection"]


class ResultsReporter:
    """
    Generates reports from SWE-bench evaluation results.
    """
    
    def __init__(self, results: Dict[str, Any]):
        """
        Initialize reporter with results.
        
        Args:
            results: Evaluation results dictionary
        """
        self.results = results
        self.timestamp = datetime.utcnow()
    
    def generate_markdown_report(self) -> str:
        """
        Generate a markdown report.
        
        Returns:
            Markdown formatted report string
        """
        sections = []
        
        # Header
        header = f"""# SWE-bench Evaluation Report

**Generated:** {self.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")}

---

## Executive Summary

"""
        sections.append(header)
        
        # Summary metrics
        summary = self._generate_summary_section()
        sections.append(summary)
        
        # Resolution analysis
        resolution = self._generate_resolution_section()
        sections.append(resolution)
        
        # Performance analysis
        performance = self._generate_performance_section()
        sections.append(performance)
        
        # Pattern analysis
        patterns = self._generate_patterns_section()
        sections.append(patterns)
        
        # Task details
        tasks = self._generate_tasks_section()
        sections.append(tasks)
        
        # Recommendations
        recommendations = self._generate_recommendations_section()
        sections.append(recommendations)
        
        return "\n".join(sections)
    
    def _generate_summary_section(self) -> str:
        """Generate summary section."""
        r = self.results
        
        status = "✅ PASSED" if r.get("resolution_rate", 0) >= 0.20 else "❌ BELOW TARGET"
        
        return f"""### Key Metrics

| Metric | Value |
|--------|-------|
| Total Tasks | {r.get("total_tasks", 0)} |
| Resolved | {r.get("resolved", 0)} |
| Failed | {r.get("failed", 0)} |
| Errors | {r.get("errors", 0)} |
| Timeouts | {r.get("timeouts", 0)} |
| **Resolution Rate** | **{r.get("resolution_rate", 0):.1%}** |
| Target | 20%+ |
| Status | {status} |

"""
    
    def _generate_resolution_section(self) -> str:
        """Generate resolution analysis section."""
        r = self.results
        task_results = r.get("task_results", [])
        
        if not task_results:
            return "### Resolution Analysis\n\nNo task results available.\n"
        
        # Group by status
        status_counts = {}
        for tr in task_results:
            status = tr.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        section = """## Resolution Analysis

### Status Distribution

| Status | Count | Percentage |
|--------|-------|------------|
"""
        
        total = len(task_results)
        for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
            pct = count / total * 100
            section += f"| {status} | {count} | {pct:.1f}% |\n"
        
        # Resolution rate by repository
        section += "\n### Resolution Rate by Repository\n\n"
        
        repo_stats = {}
        for tr in task_results:
            repo = tr.get("instance_id", "").split("-")[0]
            if repo not in repo_stats:
                repo_stats[repo] = {"total": 0, "resolved": 0}
            repo_stats[repo]["total"] += 1
            if tr.get("status") == "resolved":
                repo_stats[repo]["resolved"] += 1
        
        section += "| Repository | Resolved | Total | Rate |\n"
        section += "|------------|----------|-------|------|\n"
        
        for repo, stats in sorted(repo_stats.items(), key=lambda x: -x[1]["resolved"]):
            rate = stats["resolved"] / stats["total"] * 100 if stats["total"] > 0 else 0
            section += f"| {repo} | {stats['resolved']} | {stats['total']} | {rate:.1f}% |\n"
        
        return section + "\n"
    
    def _generate_performance_section(self) -> str:
        """Generate performance analysis section."""
        r = self.results
        task_results = r.get("task_results", [])
        
        section = """## Performance Analysis

"""
        
        # Token usage
        tokens = r.get("total_tokens", {})
        section += f"""### Token Usage

| Metric | Value |
|--------|-------|
| Total Tokens | {tokens.get("total_tokens", 0):,} |
| Input Tokens | {tokens.get("input_tokens", 0):,} |
| Output Tokens | {tokens.get("output_tokens", 0):,} |

"""
        
        # Execution time
        if task_results:
            times = [tr.get("execution_time_seconds", 0) for tr in task_results]
            avg_time = sum(times) / len(times)
            max_time = max(times)
            min_time = min(times)
            
            section += f"""### Execution Time

| Metric | Value |
|--------|-------|
| Average | {avg_time:.1f}s |
| Maximum | {max_time:.1f}s |
| Minimum | {min_time:.1f}s |

"""
        
        # Cost analysis
        cost = r.get("total_cost_estimate", 0)
        section += f"""### Cost Analysis

| Metric | Value |
|--------|-------|
| Total Cost | ${cost:.2f} |
| Avg Cost per Task | ${cost / len(task_results):.2f} |
| Cost per Resolution | ${cost / max(r.get("resolved", 1), 1):.2f} |

"""
        
        return section
    
    def _generate_patterns_section(self) -> str:
        """Generate patterns analysis section."""
        patterns = self.results.get("patterns", {})
        
        section = """## Pattern Analysis

"""
        
        # Success tools
        success_tools = patterns.get("common_success_tools", {})
        if success_tools:
            section += "### Tools Used in Successful Resolutions\n\n"
            section += "| Tool | Usage Count |\n"
            section += "|------|-------------|\n"
            for tool, count in list(success_tools.items())[:10]:
                section += f"| {tool} | {count} |\n"
            section += "\n"
        
        # Failure reasons
        failure_reasons = patterns.get("common_failure_reasons", {})
        if failure_reasons:
            section += "### Common Failure Reasons\n\n"
            section += "| Reason | Count |\n"
            section += "|--------|-------|\n"
            for reason, count in list(failure_reasons.items())[:10]:
                section += f"| {reason[:50]}... | {count} |\n"
            section += "\n"
        
        # Iteration stats
        avg_success = patterns.get("avg_iterations_success", 0)
        avg_failure = patterns.get("avg_iterations_failure", 0)
        
        section += f"""### Iteration Statistics

| Metric | Value |
|--------|-------|
| Avg Iterations (Success) | {avg_success:.1f} |
| Avg Iterations (Failure) | {avg_failure:.1f} |

"""
        
        return section
    
    def _generate_tasks_section(self) -> str:
        """Generate task details section."""
        task_results = self.results.get("task_results", [])
        
        section = """## Task Details

<details>
<summary>Click to expand task results</summary>

"""
        
        for tr in task_results:
            status_icon = "✅" if tr.get("status") == "resolved" else "❌"
            section += f"""### {status_icon} {tr.get("instance_id", "unknown")}

- **Status:** {tr.get("status", "unknown")}
- **Execution Time:** {tr.get("execution_time_seconds", 0):.1f}s
- **Iterations:** {tr.get("iterations", 0)}
- **Tools Called:** {len(tr.get("tools_called", []))}
"""
            
            if tr.get("error"):
                section += f"- **Error:** {tr.get('error')[:200]}\n"
            
            section += "\n"
        
        section += "</details>\n\n"
        return section
    
    def _generate_recommendations_section(self) -> str:
        """Generate recommendations section."""
        resolution_rate = self.results.get("resolution_rate", 0)
        patterns = self.results.get("patterns", {})
        
        section = """## Recommendations

"""
        
        recommendations = []
        
        if resolution_rate < 0.20:
            recommendations.append(
                "1. **Resolution rate below target (20%)** - Consider:\n"
                "   - Increasing max_tool_iterations for complex tasks\n"
                "   - Improving system prompt for better task understanding\n"
                "   - Adding repository-specific context loading"
            )
        
        avg_failure_iters = patterns.get("avg_iterations_failure", 0)
        if avg_failure_iters > 20:
            recommendations.append(
                "2. **High iteration count on failures** - Tasks may be getting stuck:\n"
                "   - Add early termination conditions\n"
                "   - Improve error recovery strategies\n"
                "   - Consider task decomposition for complex issues"
            )
        
        success_tools = patterns.get("common_success_tools", {})
        if "read_file" not in success_tools:
            recommendations.append(
                "3. **Low file reading in successes** - May indicate:\n"
                "   - Tasks being solved without understanding context\n"
                "   - Need for better exploration strategies"
            )
        
        if not recommendations:
            recommendations.append(
                "✅ Performance meets target. Continue monitoring and iterate on:\n"
                "- Reducing execution time\n"
                "- Improving error handling\n"
                "- Expanding test coverage"
            )
        
        section += "\n\n".join(recommendations)
        return section + "\n"
    
    def save_report(self, output_path: Path) -> None:
        """
        Save report to file.
        
        Args:
            output_path: Path to save report
        """
        report = self.generate_markdown_report()
        
        with open(output_path, "w") as f:
            f.write(report)
        
        logger.info(f"Report saved to {output_path}")


def generate_comparison_report(
    results_list: List[Dict[str, Any]],
    labels: List[str]
) -> str:
    """
    Generate a comparison report across multiple evaluation runs.
    
    Args:
        results_list: List of evaluation results
        labels: Labels for each result set
        
    Returns:
        Markdown comparison report
    """
    report = f"""# SWE-bench Comparison Report

**Generated:** {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}

## Resolution Rate Comparison

| Run | Tasks | Resolved | Rate |
|-----|-------|----------|------|
"""
    
    for label, results in zip(labels, results_list):
        rate = results.get("resolution_rate", 0)
        total = results.get("total_tasks", 0)
        resolved = results.get("resolved", 0)
        report += f"| {label} | {total} | {resolved} | {rate:.1%} |\n"
    
    report += "\n## Cost Comparison\n\n"
    report += "| Run | Cost | Cost/Resolution |\n"
    report += "|-----|------|----------------|\n"
    
    for label, results in zip(labels, results_list):
        cost = results.get("total_cost_estimate", 0)
        resolved = max(results.get("resolved", 1), 1)
        report += f"| {label} | ${cost:.2f} | ${cost/resolved:.2f} |\n"
    
    return report
