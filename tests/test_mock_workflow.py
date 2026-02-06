"""
Integration test using local LLM and Crawl4AI for web content extraction.

Prerequisites:
1. Local LLM server running at http://host.docker.internal:12434 (or configured in test_model_config.py)
2. Crawl4AI Docker container running on the host:
   docker run -d -p 11235:11235 --name crawl4ai --shm-size=1g unclecode/crawl4ai:latest
   (Tests access it via http://host.docker.internal:11235 from inside the test container)
   
This test demonstrates:
- MCP tool integration (Finance, GraphRAG)
- Crawl4AI web content extraction (replacing WebSearchAgent)
- Local LLM inference (replacing OpenRouter)
"""

import json
import asyncio
import sys
import logging
from datetime import datetime
from pathlib import Path

# Fix path to include project root
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from multi_agent_investment import (
    Agent, 
    ResearchResult, 
    McpToolProvider, 
    WebSearchAgent, 
    InternalAgentAdapter, 
    AgentSpecLoader
)
from llm_client import LocalLlmClient
from tests.test_model_config import settings
from tests.crawl4ai_agent import Crawl4AiAgent
from mcp import StdioServerParameters

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_integration_workflow():
    """
    Verifies the modular orchestration logic using 3 test agents and a LOCAL LLM.
    Agent A: Uses MCP GraphRAG + Finance
    Agent B: Uses Crawl4AI for web content extraction
    Agent C: Synthesizes A and B
    """
    
    # 1. Load Agent Profiles
    agents_dir = Path(__file__).parent / "agent-defs"
    
    def load_profile(filename):
        with open(agents_dir / filename, 'r') as f:
            return AgentSpecLoader.loadFromMarkdown(f.read())

    profile_a = load_profile("test_specialist.md")
    profile_b = load_profile("test_researcher.md")
    profile_c = load_profile("test_synthesizer.md")

    # 2. Setup Real Clients & Providers
    # Use LocalLlmClient instead of Mock
    llm_client = LocalLlmClient(
        baseUrl=settings.LLM_URL, 
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        maxTokens=settings.LLM_MAX_TOKENS
    )
    
    # Real MCP Provider for Agent A (Finance)
    finance_provider = McpToolProvider("finance", StdioServerParameters(
        command="docker",
        args=["run", "-i", "--rm", settings.FINANCE_TOOLS_IMAGE]
    ))
    
    # Real MCP Provider for Agent A (GraphRAG)
    # Note: We use minimalist args for testing.
    graphrag_provider = McpToolProvider("graphrag", StdioServerParameters(
        command="docker",
        args=["run", "-i", "--rm", settings.GRAPHRAG_IMAGE, "npx", "tsx", "mcp_server.ts"]
    ))

    # Web Crawling for Agent B using Crawl4AI
    # --- COMMENTED OUT: Original WebSearchAgent using OpenRouter ---
    # import internal_configs as cfg
    # webSearchModel = cfg.config.WEB_SEARCH_MODEL
    # web_search_agent = WebSearchAgent(cfg.config.OPENROUTER_API_KEY, model=webSearchModel)
    # web_adapter = InternalAgentAdapter("web", web_search_agent)
    # --- END COMMENTED OUT ---
    
    # Use host.docker.internal to reach host machine from inside Docker container
    crawl4ai_agent = Crawl4AiAgent(baseUrl="http://host.docker.internal:11235")

    # 4. Initialize Agents
    agent_a = Agent(profile_a, llm_client, model=settings.LLM_MODEL, mcpProvider=finance_provider)
    # Agent B will directly use crawl4ai_agent - no adapter needed for now
    agent_c = Agent(profile_c, llm_client, model=settings.LLM_MODEL)

    # 5. Execute Workflow
    try:
        # Connect providers
        await finance_provider.connect()
        await graphrag_provider.connect()
        
        logger.info("Executing Agent A task...")
        res_a_text = await agent_a.performResearchTask("Check the latest stock prices for Energy Fuels (UUUU) using finance tools.")
        
        logger.info("Executing Agent B task...")
        # Use Crawl4AI to fetch the JSON content directly
        # target_url = "http://arduino.esp8266.com/stable/package_esp8266com_index.json"
        target_url="https://www.sec.gov/edgar/search/#/dateRange=1y&ciks=0001801368&entityName=MP%2520Materials%2520Corp.%2520%252F%2520DE%2520(MP)%2520(CIK%25200001801368)"
        crawled_content = await crawl4ai_agent.fetchUrl(target_url, extractMarkdown=False)
        
        # Now ask the LLM to analyze the fetched content
        res_b_text = await agent_c.performResearchTask(
            f"Dive through the Insider trading report and calculate the total volumes traded:\n\n{crawled_content[:5000]}"
        )
        
        logger.info(f"Agent B result (via Crawl4AI): {res_b_text}")

        # Synthesis Phase
        logger.info("Executing Synthesis Phase...")
        synthesis_prompt = f"Summarize the findings from our specialists.\nTool Specialist (Agent A): {res_a_text}\nWeb Researcher (Agent B): {res_b_text}"
        final_output = await agent_c.performResearchTask(synthesis_prompt)

        logger.info("\n=== INTEGRATION TEST COMPLETE ===")
        logger.info(f"Final Synthesis: {final_output}")
        
    finally:
        await finance_provider.cleanup()
        await graphrag_provider.cleanup()

if __name__ == "__main__":
    asyncio.run(test_integration_workflow())
