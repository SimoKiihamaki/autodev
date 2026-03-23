"""
Test suite for the hierarchical agent pipeline.

This module contains unit and integration tests for:
- AgentPipeline: Main pipeline integrating agents with training infrastructure
- AgentTrainingBridge: Bridge connecting agents to training infrastructure
- HierarchicalExecutor: Orchestrates Manager → Coder → Reviewer flow
- TrainedModelProvider: Provides trained models to agents
- AgentTraceCollector: Collects execution traces from agents

Test Coverage Requirements:
- AgentPipeline: 90%
- AgentTrainingBridge: 95%
- HierarchicalExecutor: 90%
- TrainedModelProvider: 85%
- AgentTraceCollector: 90%
"""

__all__ = []
