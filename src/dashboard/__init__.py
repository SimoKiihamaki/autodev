"""
AutoDev Dashboard Module

Real-time TUI dashboard for monitoring the AutoDev training pipeline.
"""

from .metrics_dashboard import (
    MetricsDashboard,
    DashboardMetrics,
    create_dashboard,
)

__all__ = [
    "MetricsDashboard",
    "DashboardMetrics",
    "create_dashboard",
]
