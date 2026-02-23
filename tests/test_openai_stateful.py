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
from agent_engine import Agent, AgentSpecLoader, McpToolProvider
from mcp import StdioServerParameters

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
        
        # Initialize GraphRAG Tool Provider for tool-calling test
        registryPath = cfg.config.GRAPHRAG_REGISTRY_DIR
        projectHomePath = cfg.config.GRAPHRAG_PROJECT_PATH
        
        self.provider = McpToolProvider("graphrag", StdioServerParameters(
            command="docker",
            args=[
                "run", "-i", "--rm",
                "-v", f"{projectHomePath}:/app",
                "-v", f"{cfg.config.GRAPHRAG_NODE_MODULES_VOLUME}:/app/node_modules",
                "-v", f"{registryPath}:/root/.graphrag",
                "-v", f"{projectHomePath}/.DuckDB:/app/.DuckDB",
                "-v", f"{projectHomePath}/output:/app/output",
                "--add-host=host.docker.internal:host-gateway",
                "-e", f"OPENROUTER_API_KEY={api_key}",
                "-e", f"GRAPHRAG_DATABASE={cfg.config.GRAPHRAG_DATABASE}",
                "-e", f"R2_DB_URL={cfg.config.R2_DB_URL}",
                "-e", "PYTHONUNBUFFERED=1",
                "-e", "NODE_NO_WARNINGS=1",
                cfg.config.GRAPHRAG_IMAGE
            ],
            env=None
        ))
        await self.provider.connect()

        self.agent = Agent(
            profile=self.profile, 
            llmClient=self.client, 
            model=self.model,
            mcpProvider=self.provider
        )

        logger.info(f"Live Test Setup: Agent [{self.profile.name}] using model [{self.model}] via OpenRouter SDK")

    async def asyncTearDown(self):
        """Cleanup tool providers."""
        if hasattr(self, 'provider'):
            await self.provider.cleanup()

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
        
        self.assertTrue(len(self.agent.messageHistory) >= 3) # System + User + Assistant
        self.assertIsNotNone(self.agent.lastResponse.id)
        self.assertTrue("total_tokens" in self.agent.lastResponse.usage)
        
        # Turn 2: Injected Tool Call (Corpus Health Check)
        q_health = "Wait, before we continue, perform a health check on the knowledge graph to ensure it's loaded correctly."
        logger.info(f"Injected Health Turn: {q_health}")
        res_health = await self.agent.performResearchTask(q_health)
        self._printPrettyResponse(2)
        
        # Verify tool call was likely made
        self.assertTrue(len(self.agent.messageHistory) >= 5) # (System, U1, A1, U_H, A_H)
        
        # Turn 3: Updated Prior Turn 2 (Reflecting health check + original context)
        q3 = "Now, based on that health check and our previous discussion about Rocket Lab, how well is the 'haste' program represented in the corpus?"
        logger.info(f"Turn 3 Query: {q3}")
        
        res3 = await self.agent.performResearchTask(q3)
        self._printPrettyResponse(3)
        
        # Validation Logic for Context
        context_keywords = ["Rocket Lab", "Hypersonic", "Test", "Electron", "Suborbital", "HASTE", "Corpus", "Health", "Stats"]
        found_context = any(word.lower() in res3.lower() for word in context_keywords)
        
        self.assertTrue(found_context, 
            "Turn 3 response failed to maintain context or reflect the health check.")
        
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
