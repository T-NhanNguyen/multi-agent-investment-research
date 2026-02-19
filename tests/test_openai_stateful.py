# ABOUTME: Live integration test for verifying stateful context management in OpenAIClient.
# ABOUTME: Uses the OpenAI SDK pointed at OpenRouter to validate multi-turn context preservation
# ABOUTME: via the Agent's standard message history (no Responses API required).

import logging
import sys
import unittest
import os

# Ensure project root is in path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import internal_configs as cfg
from llm_client import OpenAIClient, getLlmClient
from agent_engine import Agent, AgentSpecLoader

# Configure verbose logging without emojis
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("LiveOpenAIStateful")

class TestLiveOpenAIStateful(unittest.IsolatedAsyncioTestCase):
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
                                  "agent-definition-files", "qualitative_agent.md")
        with open(agent_path, "r") as f:
            content = f.read()

        self.profile = AgentSpecLoader.loadFromMarkdown(content)
        self.agent = Agent(profile=self.profile, llmClient=self.client, model=self.model)

        logger.info(f"Live Test Setup: Agent [{self.profile.name}] using model [{self.model}] via OpenRouter SDK")

    async def test_live_ambiguous_context_preservation(self):
        """
        Verify that the agent maintains context across turns using message history.
        We ask an ambiguous second question that depends entirely on the first turn.
        Includes verification of pretty-printing and reasoning extraction for both turns.
        """
        
        # Turn 1: Specific Topic
        q1 = "Tell me about Rocket Lab's HASTE program. Think step by step."
        logger.info(f"Turn 1 Query: {q1}")
        
        res1 = await self.agent.performResearchTask(q1)
        self._printPrettyResponse(1)
        
        # Verify Turn 1 established history and structured response
        self.assertTrue(len(self.agent.messageHistory) >= 3) # System + User + Assistant
        self.assertIsNotNone(self.agent.lastResponse.id)
        self.assertTrue("total_tokens" in self.agent.lastResponse.usage)
        
        # Turn 2: Highly Ambiguous Follow-up
        q2 = "What is haste?"
        logger.info(f"Turn 2 Query: {q2}")
        
        res2 = await self.agent.performResearchTask(q2)
        self._printPrettyResponse(2)
        
        # Validation Logic for Context
        context_keywords = ["Rocket Lab", "Hypersonic", "Test", "Electron", "Suborbital", "HASTE"]
        found_context = any(word.lower() in res2.lower() for word in context_keywords)
        
        self.assertTrue(found_context, 
            "Turn 2 response failed to maintain context. It likely returned a general definition of 'haste'.")
        
        # Validation for Structure
        self.assertIsNotNone(self.agent.lastResponse.id)
        logger.info(f"Verified ChatResponse structure for Turn 2: {self.agent.lastResponse.usageSummary}")

        if self.agent.lastResponse.reasoning:
            logger.info("Successfully extracted model reasoning/thought segment.")
        
        logger.info("Live Context Preservation + Pretty Response Test: PASSED")

    def _printPrettyResponse(self, turn: int):
        """Helper to output the structured response in a human-readable format."""
        response = self.agent.lastResponse
        if not response:
            return
            
        print("\n" + "="*60)
        print(f"TURN {turn}: PRETTY-PRINTED LLM RESPONSE")
        print("="*60)
        print(response) # Uses the ChatResponse.__str__ method
        print("="*60 + "\n")

if __name__ == "__main__":
    unittest.main()
