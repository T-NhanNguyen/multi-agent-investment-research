import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path
import sys
# Fix path to include project root
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

# Explicitly import from our NEW refactored engine to ensure it's being tested
from agent_engine import Agent, AgentSpecLoader, AgentProfile
from multi_agent_investment import ResearchOrchestrator

class TestAgentEngine(unittest.IsolatedAsyncioTestCase):
    """
    Tests the core components of agent_engine.py to ensure the refactor is functional.
    """

    def test_spec_loader(self):
        """Verifies AgentSpecLoader correctly parses markdown into AgentProfile."""
        mock_md = "# Test Agent\n## Specialization\nTest specialist\n## Skills\n- Skill 1\n## Personality\n- Precise"
        profile = AgentSpecLoader.loadFromMarkdown(mock_md)
        
        self.assertIsInstance(profile, AgentProfile)
        self.assertEqual(profile.name, "Test Agent")
        self.assertEqual(profile.specialization, "Test specialist")
        self.assertIn("Skill 1", profile.skills)

    async def test_agent_logic_and_history(self):
        """
        Tests agent_engine.Agent for correct history management and tool routing.
        This tests the actual code in agent_engine.py without real LLM/MCP.
        """
        profile = AgentProfile("Test", ["tools"], ["friendly"], "test", "System Prompt")
        mock_llm = MagicMock()
        mock_llm.chatCompletion = AsyncMock(return_value={
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "Hello world"
                }
            }]
        })

        agent = Agent(profile, mock_llm)
        
        # 1. Perform task
        response = await agent.performResearchTask("Tell me about stocks")
        
        # Verify component behavior from agent_engine.py
        self.assertEqual(response, "Hello world")
        # History: [SystemPrompt, UserQuery, AssistantResponse]
        self.assertEqual(len(agent.messageHistory), 3) 
        self.assertEqual(agent.messageHistory[0]["role"], "system")
        self.assertEqual(agent.messageHistory[1]["role"], "user")
        self.assertEqual(agent.messageHistory[2]["role"], "assistant")
        
        # 2. Verify history persistence (the core of our agentic state)
        await agent.performResearchTask("Follow up")
        # History: [System, User1, Assist1, User2, Assist2]
        self.assertEqual(len(agent.messageHistory), 5) 

    async def test_orchestrator_integration(self):
        """
        Verifies ResearchOrchestrator correctly integrates the refactored Agent classes.
        """
        # Mock LLM to simulate a short fundamental research session
        mock_llm = MagicMock()
        mock_llm.chatCompletion = AsyncMock()
        
        # Mock responses for: Synthesis Initial -> Quant -> Qual -> Synthesis Final -> Thesis
        mock_llm.chatCompletion.side_effect = [
            {"choices": [{"message": {"role": "assistant", "content": "## For Quantitative Agent:\nPrice\n## For Qualitative Agent:\nNews"}}]},
            {"choices": [{"message": {"role": "assistant", "content": "Price is 100"}}]},
            {"choices": [{"message": {"role": "assistant", "content": "News is good"}}]},
            {"choices": [{"message": {"role": "assistant", "content": "Done"}}]},
            {"choices": [{"message": {"role": "assistant", "content": "# Final Thesis\nBuy" }}]}
        ]

        with patch('multi_agent_investment.getLLMClient', return_value=mock_llm), \
             patch('agent_engine.McpToolProvider.connect', new_callable=AsyncMock), \
             patch('agent_engine.McpToolProvider.cleanup', new_callable=AsyncMock):
            
            orchestrator = ResearchOrchestrator(mode="fundamental")
            
            # This triggers the real logic in Agent and Orchestrator
            result = await orchestrator.executeResearchSession("BMER", exportReport=False)
            
            self.assertIn("# Final Thesis", result["agents"]["synthesis"]["finalRecommendation"])
            # Ensure the orchestrator's synthesis agent is actually an instance of our new Agent class
            self.assertIsInstance(orchestrator.synthesisAgent, Agent)

if __name__ == "__main__":
    unittest.main()
