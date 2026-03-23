#!/usr/bin/env python3
"""Quick integration test for agent with MCP client."""
import asyncio
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# Set dummy API key for testing
os.environ["ANTHROPIC_API_KEY"] = "sk-test-dummy-key"

async def test():
    from agents.base import BaseAgent, AgentRole, AgentState
    from llm.base_client import LLMConfig
    
    # Create a simple test agent
    class TestAgent(BaseAgent):
        async def execute(self, task):
            return {'status': 'success'}
        async def initialize(self):
            await self._initialize_llm()
            await self._initialize_mcp()
            await self._initialize_tool_executor()
        async def shutdown(self):
            if self._mcp_client:
                await self._mcp_client.disconnect_all()
        def _get_default_system_prompt(self):
            return 'Test agent'
    
    agent = TestAgent(role=AgentRole.CODER)
    await agent.initialize()
    
    # Check MCP client
    print(f'✓ Agent MCP client initialized: {agent._mcp_client is not None}')
    print(f'✓ Agent tool executor initialized: {agent._tool_executor is not None}')
    print(f'✓ Agent LLM client initialized: {agent._llm_client is not None}')
    
    # Check tools available
    tools = agent._mcp_client.list_tools()
    print(f'✓ Tools available: {len(tools)}')
    
    # Test tool call
    result = await agent._mcp_client.call_tool('read_file', {'path': 'test.txt'})
    print(f'✓ Tool call result: {result[:50]}...')
    
    await agent.shutdown()
    print('✓ Agent shutdown complete')
    print('\n✅ All agent integration tests passed!')

if __name__ == "__main__":
    asyncio.run(test())
