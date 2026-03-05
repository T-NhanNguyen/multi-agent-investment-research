# ABOUTME: Simple test script to instantiate the Quantitative Agent with the FinvizAdapter
# ABOUTME: and verify it can successfully hit the get_finviz_data tool and pull a specific key.

import logging
import sys
import unittest
import os
import json

# Ensure project root is in path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import internal_configs as cfg
from llm_client import OpenAIClient
from agent_engine import Agent, AgentSpecLoader
from scrapers import FinvizScraper
from multi_agent_investment import FinvizAdapter

# Configure verbose logging without emojis
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("TestFinvizAgent")

class TestFinvizAgent(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Use OpenRouter key + base URL — the SDK is fully compatible
        api_key = cfg.config.OPENROUTER_API_KEY
        base_url = OpenAIClient.OPENROUTER_BASE_URL
        self.model = cfg.config.PRIMARY_MODEL

        if not api_key:
            self.skipTest("No OPENROUTER_API_KEY found in environment. Skipping live test.")

        # Initialize the SDK-based client pointed at OpenRouter
        self.client = OpenAIClient(apiKey=api_key, baseUrl=base_url)

        # Load a real agent profile
        agent_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                  "agent-definition-files", "quantitative_agent.md")
        with open(agent_path, "r") as f:
            content = f.read()

        self.profile = AgentSpecLoader.loadFromMarkdown(content)
        
        # Initialize Finviz Scraper and Adapter
        self.finvizScraper = FinvizScraper()
        self.finvizAdapter = FinvizAdapter("finviz", self.finvizScraper)

        # We inject the FinvizAdapter directly to the Agent to test tool routing.
        self.agent = Agent(
            profile=self.profile, 
            llmClient=self.client, 
            model=self.model,
            agentAdapter=self.finvizAdapter
        )

        logger.info(f"Live Test Setup: Agent [{self.profile.name}] using model [{self.model}] via OpenRouter SDK")

    async def test_finviz_cache_and_filter(self):
        """
        Test the two-step Finviz workflow:
        1. Inject a command to force get_finviz_data caching
        2. Ask the agent to use filter_finviz_data to pull a specific section.
        """
        ticker = "NVDA"
        
        # Step 1: Force cache warm-up (simulate Synthesis agent step)
        logger.info(f"Step 1: Manually triggering cache warmup for {ticker}")
        warmup_res = await self.finvizAdapter.executeMcpTool("get_finviz_data", {"ticker": ticker})
        self.assertTrue("SUCCESS" in warmup_res)
        logger.info(warmup_res)

        # Step 2: Have the Quantitative agent pull the fundamentals using filter_finviz_data
        q1 = f"Please use your filter_finviz_data tool to extract the 'fundamentals' for {ticker} from your cache, and tell me the Market Cap."
        logger.info(f"Turn 1 Query: {q1}")
        
        res1 = await self.agent.performResearchTask(q1)
        
        self.assertIsNotNone(self.agent.lastResponse.id)
        self.assertTrue("Market Cap" in res1, "Agent failed to retrieve or report the Market Cap.")
        
        print("\n" + "="*60)
        print("AGENT RESPONSE:")
        print("="*60)
        print(self.agent.lastResponse.content)
        print("="*60)
        print(f"Usage Summary: {self.agent.lastResponse.usageSummary}")

if __name__ == "__main__":
    unittest.main()
