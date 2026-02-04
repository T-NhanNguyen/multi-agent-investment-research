import os
import asyncio
import json
import logging
import httpx
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from contextlib import AsyncExitStack
from dotenv import load_dotenv

# MCP Imports
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- MCP CONFIGURATION ---
# Define your Docker commands exactly as you tested them
MCP_SERVERS = {
    "finance": StdioServerParameters(
        command="docker",
        args=["run", "-i", "--rm", "finance-tools"], # Add your specific args here
        env=None
    ),
    # Add graphrag similarly if needed
}

class MCPBridge:
    """Bridges OpenRouter API with Local Docker MCP Servers"""
    
    def __init__(self, server_params: StdioServerParameters):
        self.server_params = server_params
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.tools_map = {} # Cache tool definitions

    async def connect(self):
        """Establishes stdio connection to the Docker container"""
        logger.info(f"Connecting to MCP Server: {self.server_params.command}...")
        
        # Start the stdio transport
        transport = await self.exit_stack.enter_async_context(
            stdio_client(self.server_params)
        )
        self.read, self.write = transport
        
        # Start the MCP session
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(self.read, self.write)
        )
        await self.session.initialize()
        
        # Fetch available tools and cache them
        result = await self.session.list_tools()
        self.tools_map = {tool.name: tool for tool in result.tools}
        logger.info(f"Connected. Loaded {len(self.tools_map)} tools.")

    async def get_openai_tools(self) -> List[Dict]:
        """Convert MCP tool definitions to OpenRouter/OpenAI format"""
        if not self.session:
            await self.connect()
            
        openai_tools = []
        for tool in self.tools_map.values():
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema # MCP inputSchema maps 1:1 to OpenAI parameters
                }
            })
        return openai_tools

    async def call_tool(self, name: str, arguments: Dict) -> Any:
        """Execute the tool on the Docker container"""
        if not self.session:
            raise RuntimeError("MCP Session not connected")
            
        logger.info(f"Executing MCP Tool: {name}")
        result = await self.session.call_tool(name, arguments)
        
        # Format result as string for the LLM
        return result.content[0].text

    async def cleanup(self):
        await self.exit_stack.aclose()