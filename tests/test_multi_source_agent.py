import asyncio
import logging
import json
import sys
import os

# Add parent directory to path to allow absolute imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_engine import (
    Agent, 
    AgentSpecLoader, 
    FinvizAdapter, 
    RobinhoodAdapter, 
    InternalAgentAdapter,
    WebSearchAgent,
    CompositeAgentAdapter
)
from scrapers import FinvizScraper, RobinhoodScraper
from llm_client import getLlmClient
import internal_configs as cfg

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestMultiSource")

# Sample Agent Persona for testing
AGENT_SPEC = """
# Data Verification Agent
## Skills
- Multi-source cross-referencing
- Financial data extraction
- Sentiment analysis

## Personality
- Precise
- Skeptical
- Analytical

## Specialization
You are a specialist in verifying financial data across multiple platforms. 
Your goal is to compare data from Finviz and Robinhood to ensure consistency.
"""

async def test_multi_source_integration():
    logger.info("Starting Multi-Source Integration Test (Robinhood + Finviz)...")
    
    # Initialize components
    apiKey = cfg.config.OPENROUTER_API_KEY
    if not apiKey:
        logger.error("Missing OPENROUTER_API_KEY")
        return

    llmClient = getLlmClient(provider="openrouter", model=cfg.config.PRIMARY_MODEL, apiKey=apiKey)
    
    finviz = FinvizScraper()
    finviz_adapter = FinvizAdapter("finviz", finviz)
    
    robinhood = RobinhoodScraper()
    robinhood_adapter = RobinhoodAdapter("robinhood", robinhood)
    
    web_search = WebSearchAgent(apiKey)
    web_search_adapter = InternalAgentAdapter("web-search", web_search)
    
    composite = CompositeAgentAdapter([
        finviz_adapter,
        robinhood_adapter,
        web_search_adapter
    ])
    
    profile = AgentSpecLoader.loadFromMarkdown(AGENT_SPEC)
    agent = Agent(profile, llmClient, agentAdapter=composite)
    
    # Test Query
    query = (
        "Verify the current stats for TSLA. "
        "1. Get data from Finviz (get_finviz_data). "
        "2. Get data from Robinhood (get_robinhood_data). "
        "3. Use filter_finviz_data and filter_robinhood_data to compare Market Cap and Analyst Ratings. "
        "Summarize any discrepancies."
    )
    
    logger.info(f"Running task: {query}")
    response = await agent.performResearchTask(query)
    
    print("\n" + "="*50)
    print("AGENT VERIFICATION RESPONSE:")
    print("="*50)
    print(response)
    print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(test_multi_source_integration())
