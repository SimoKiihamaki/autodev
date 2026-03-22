#!/usr/bin/env python3
"""
AutoDev Phase 2 - Usage Example

This example demonstrates how to use the LLM/MCP integration
to create and execute a development task.
"""

import asyncio
import logging
from pathlib import Path

# Import AutoDev components
from autodev.agents import ManagerAgent, CoderAgent, ReviewerAgent
from autodev.base import TaskSpec, TaskResult
from autodev.llm import LLMConfig
from autodev.mcp import AutoDevMCPClient


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def example_simple_feature():
    """
    Example: Implement a simple feature using the Manager Agent.
    
    This demonstrates the full workflow:
    1. Manager decomposes the task
    2. Coder implements the feature
    3. Reviewer validates the code
    4. Manager synthesizes results
    """
    logger.info("Starting simple feature implementation example")
    
    # Create task specification
    task = TaskSpec(
        task_type="implement",
        specification="""
        Implement a simple calculator module with the following functions:
        - add(a, b): Add two numbers
        - subtract(a, b): Subtract b from a
        - multiply(a, b): Multiply two numbers
        - divide(a, b): Divide a by b (with zero check)
        
        Requirements:
        - Include proper error handling
        - Add docstrings to all functions
        - Follow PEP 8 style guidelines
        """,
        target_files=["calculator.py"],
        constraints={
            "preserve_api": False,
            "maintain_coverage": True,
            "acceptance_criteria": [
                "All four operations are implemented",
                "Zero division is handled gracefully",
                "All functions have docstrings"
            ]
        },
        verification_command="pytest tests/test_calculator.py -v",
        timeout_seconds=300
    )
    
    # Initialize Manager Agent
    manager = ManagerAgent(
        mcp_config_path="~/.config/autodev/mcp_config.json",
        repo_root=".",
        max_concurrent_workers=2,
        task_timeout_seconds=300
    )
    
    try:
        # Initialize the manager (connects to LLM and MCP)
        await manager.initialize()
        logger.info("Manager agent initialized")
        
        # Execute the task
        result = await manager.execute(task)
        
        # Display results
        logger.info(f"Task completed with status: {result.status}")
        logger.info(f"Files modified: {result.files_modified}")
        logger.info(f"Summary: {result.summary}")
        
        if result.error:
            logger.error(f"Task error: {result.error}")
        
        return result
        
    finally:
        # Clean shutdown
        await manager.shutdown()
        logger.info("Manager agent shut down")


async def example_coder_with_tools():
    """
    Example: Coder Agent using MCP tools directly.
    
    This demonstrates how a Coder Agent uses MCP tools
    to read files, write code, and execute commands.
    """
    logger.info("Starting coder with tools example")
    
    # Initialize Coder Agent
    coder = CoderAgent(
        mcp_config_path="~/.config/autodev/mcp_config.json",
        repo_root="."
    )
    
    try:
        await coder.initialize()
        logger.info("Coder agent initialized")
        
        # Create a task
        task = TaskSpec(
            task_id="example-coder-task",
            task_type="implement",
            specification="""
            Create a Python module called 'utils.py' with a function
            'format_date(date: datetime) -> str' that formats a date
            as 'YYYY-MM-DD'.
            """,
            target_files=["utils.py"]
        )
        
        # Execute
        result = await coder.execute(task)
        
        logger.info(f"Coder completed: {result.summary}")
        logger.info(f"Modified files: {result.files_modified}")
        
        return result
        
    finally:
        await coder.shutdown()


async def example_reviewer_workflow():
    """
    Example: Reviewer Agent analyzing code changes.
    
    This demonstrates how a Reviewer Agent validates
    code quality and checks acceptance criteria.
    """
    logger.info("Starting reviewer workflow example")
    
    # First, create some code to review (using Coder)
    coder = CoderAgent()
    await coder.initialize()
    
    implement_task = TaskSpec(
        task_type="implement",
        specification="Create a simple hello.py with a hello() function",
        target_files=["hello.py"]
    )
    
    coder_result = await coder.execute(implement_task)
    await coder.shutdown()
    
    # Now review the code
    reviewer = ReviewerAgent(
        mcp_config_path="~/.config/autodev/mcp_config.json",
        repo_root=".",
        strict_mode=True
    )
    
    try:
        await reviewer.initialize()
        logger.info("Reviewer agent initialized")
        
        # Create review task
        review_task = TaskSpec(
            task_id="example-review-task",
            task_type="review",
            specification="Review the code changes in hello.py",
            target_files=["hello.py"],
            constraints={
                "acceptance_criteria": [
                    "Function is properly defined",
                    "Code follows PEP 8",
                    "No security issues"
                ]
            }
        )
        
        # Execute review
        result = await reviewer.execute(review_task)
        
        logger.info(f"Review verdict: {result.review_verdict}")
        logger.info(f"Review summary: {result.summary}")
        
        if result.result and "findings" in result.result:
            logger.info(f"Findings: {len(result.result['findings'])} issues found")
        
        return result
        
    finally:
        await reviewer.shutdown()


async def example_mcp_client_direct():
    """
    Example: Using MCP client directly without agents.
    
    This demonstrates low-level MCP tool access.
    """
    logger.info("Starting MCP client direct usage example")
    
    # Initialize MCP client
    mcp_client = AutoDevMCPClient(
        config_path="~/.config/autodev/mcp_config.json"
    )
    
    try:
        # Connect to servers
        await mcp_client.connect_all()
        logger.info(f"Connected to {len(mcp_client.sessions)} MCP servers")
        
        # List available tools
        tools = mcp_client.get_tools_for_llm()
        logger.info(f"Available tools: {[t.name for t in tools]}")
        
        # Use filesystem tool to read a file
        if "read_file" in mcp_client.tools:
            result = await mcp_client.call_tool(
                "read_file",
                {"path": "README.md"}
            )
            logger.info(f"Read README.md: {len(result)} chars")
        
        # Use git tool to get status
        if "git_status" in mcp_client.tools:
            status = await mcp_client.call_tool("git_status", {})
            logger.info(f"Git status: {status}")
        
        # Use terminal tool to run a command
        if "execute_command" in mcp_client.tools:
            output = await mcp_client.call_tool(
                "execute_command",
                {"command": "python --version"}
            )
            logger.info(f"Python version: {output}")
        
    finally:
        await mcp_client.disconnect_all()
        logger.info("MCP client disconnected")


async def example_custom_llm_config():
    """
    Example: Using custom LLM configuration.
    
    This demonstrates how to configure LLM settings
    for different use cases.
    """
    logger.info("Starting custom LLM config example")
    
    # Create custom LLM config for a task requiring more tokens
    llm_config = LLMConfig(
        provider="anthropic",
        model="claude-3-5-sonnet-20241022",
        max_tokens=8192,  # More tokens for complex tasks
        temperature=0.5,  # Lower temperature for more deterministic output
        enable_caching=True,
        timeout_seconds=180
    )
    
    # Initialize agent with custom config
    manager = ManagerAgent(
        llm_config=llm_config,
        mcp_config_path="~/.config/autodev/mcp_config.json"
    )
    
    try:
        await manager.initialize()
        
        # Complex task
        task = TaskSpec(
            task_type="implement",
            specification="Implement a complete REST API with 10 endpoints",
            timeout_seconds=600
        )
        
        result = await manager.execute(task)
        
        # Check LLM usage stats
        if manager._llm_client:
            stats = manager._llm_client.get_usage_stats()
            logger.info(f"LLM usage: {stats}")
        
        return result
        
    finally:
        await manager.shutdown()


async def main():
    """Run all examples."""
    examples = [
        ("Simple Feature Implementation", example_simple_feature),
        ("Coder with Tools", example_coder_with_tools),
        ("Reviewer Workflow", example_reviewer_workflow),
        ("MCP Client Direct", example_mcp_client_direct),
        ("Custom LLM Config", example_custom_llm_config)
    ]
    
    print("\n" + "="*80)
    print("AutoDev Phase 2 - Usage Examples")
    print("="*80 + "\n")
    
    for i, (name, example_func) in enumerate(examples, 1):
        print(f"\n{i}. {name}")
        print("-" * 80)
        
        try:
            result = await example_func()
            print(f"✓ {name} completed successfully")
            if hasattr(result, 'status'):
                print(f"  Status: {result.status}")
        except Exception as e:
            print(f"✗ {name} failed: {e}")
        
        print()
    
    print("="*80)
    print("All examples completed")
    print("="*80 + "\n")


if __name__ == "__main__":
    # Run examples
    asyncio.run(main())
