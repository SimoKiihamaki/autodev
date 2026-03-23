"""
MCP (Model Context Protocol) Integration Module

Provides MCP client implementation for AutoDev agents to access tools
through the Model Context Protocol standard.

As specified in Section 2 of the Phase 2 LLM/MCP Integration Specification.
"""

from .client import (
    AutoDevMCPClient,
    MCPServerConfig,
    MCPToolInfo,
    MCPConnectionError,
    MCPToolError,
)

__all__ = [
    "AutoDevMCPClient",
    "MCPServerConfig",
    "MCPToolInfo",
    "MCPConnectionError",
    "MCPToolError",
]
