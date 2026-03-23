"""
AutoDev - Hierarchical Agent Architecture

This package implements the Manager-Coder-Reviewer pattern for automated 
development tasks as specified in the Hierarchical Architecture Specification.

Version: 2.0.0
Phase: 2 - LLM/MCP Integration

Modules:
    - llm: LLM client implementations (Anthropic, etc.)
    - mcp: MCP (Model Context Protocol) client for tool integration
    - agents: Agent implementations (Manager, Coder, Reviewer)
"""

__version__ = "2.0.0"
__author__ = "AutoDev Agent Research"

# Lazy imports to avoid circular dependencies
def get_llm_client():
    """Get LLM client module."""
    from . import llm
    return llm

def get_mcp_client():
    """Get MCP client module."""
    from . import mcp
    return mcp

def get_agents():
    """Get agents module."""
    from . import agents
    return agents
