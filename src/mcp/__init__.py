"""
MCP (Model Context Protocol) Integration Module

Provides MCP client implementation for AutoDev agents to access tools
through the Model Context Protocol standard.

As specified in Section 2 of the Phase 2 LLM/MCP Integration Specification.
"""

from .client import (
    # Main client
    AutoDevMCPClient,
    
    # Configuration classes
    MCPServerConfig,
    MCPSecurityConfig,
    
    # Data classes
    MCPToolInfo,
    MCPResourceInfo,
    MCPPromptInfo,
    MCPServerHealth,
    MCPMetrics,
    
    # Enums
    ServerStatus,
    
    # Exceptions
    MCPConnectionError,
    MCPToolError,
    MCPSecurityError,
    MCPResourceError,
    
    # Utility
    MCP_AVAILABLE,
)

__all__ = [
    # Main client
    "AutoDevMCPClient",
    
    # Configuration classes
    "MCPServerConfig",
    "MCPSecurityConfig",
    
    # Data classes
    "MCPToolInfo",
    "MCPResourceInfo",
    "MCPPromptInfo",
    "MCPServerHealth",
    "MCPMetrics",
    
    # Enums
    "ServerStatus",
    
    # Exceptions
    "MCPConnectionError",
    "MCPToolError",
    "MCPSecurityError",
    "MCPResourceError",
    
    # Utility
    "MCP_AVAILABLE",
]
