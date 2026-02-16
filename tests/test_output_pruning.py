# ABOUTME: Integration test for strict tool isolation and token accounting.
# ABOUTME: Agent A = Web Search only, Agent B = GraphRAG only, Agent C = Finance only.
# ABOUTME: Verifies agents cannot access tools outside their designated provider.

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to sys.path
projectRoot = Path(__file__).resolve().parent.parent
sys.path.append(str(projectRoot))

from agent_engine import (
    Agent, AgentProfile, WebSearchAgent, InternalAgentAdapter, McpToolProvider
)
import internal_configs as cfg
from llm_client import OpenRouterClient
from monitoring_wrapper import state, currentAgent, patch_multi_agent, TokenUsage
from mcp import StdioServerParameters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ToolIsolationTest")


async def run_test(agentA, agentB, agentC, graphragProvider, financeProvider, use_pruning: bool = False):
    """
    Integration test verifying:
    1. Strict tool isolation (A: Web, B: GraphRAG, C: Finance)
    2. Token accounting via OpenRouter usage metrics
    3. Output pruning effectiveness (when use_pruning=True)
    
    Args:
        use_pruning: If True, applies pruneAgentOutput to each agent's result
    """

    workflowId = f"test_{'pruned' if use_pruning else 'raw'}"
    state.reset(workflowId, "RKLB Tool Isolation Validation", "test")

    # Register agents in monitoring state (must be done after reset)
    for agent in [agentA, agentB, agentC]:
        profile = agent.profile
        state.agents[profile.name] = {
            "id": profile.name.lower(),
            "name": profile.name,
            "role": profile.specialization,
            "status": "idle",
            "progress": 0,
            "usage": TokenUsage(),
            "toolCallsCount": 0,
            "currentTask": None
        }

    try:
        # --- Execute Multi-Agent Workflow (Sequential Handoffs) ---
        
        # STEP 1: Agent A performs web search
        logger.info(f"\n=== Agent A (Web Search) - {'PRUNED' if use_pruning else 'RAW'} ===")
        taskA = "Search for recent Rocket Lab (RKLB) news and summarize key developments."
        resultA = await agentA.performResearchTask(taskA)
        
        # Optionally prune Agent A's output before passing to Agent B
        contextForB = resultA
        if use_pruning:
            from output_pruner import pruneAgentOutput
            contextForB = pruneAgentOutput(resultA, agentType="qualitative")
            logger.info(f"Agent A output: {len(resultA)} chars → {len(contextForB)} chars (pruned)")
        else:
            logger.info(f"Agent A output: {len(resultA)} chars (raw)")
        
        # STEP 2: Agent B analyzes using GraphRAG with Agent A's findings as context
        logger.info(f"\n=== Agent B (GraphRAG) - {'PRUNED' if use_pruning else 'RAW'} ===")
        # Note: We provide task and context. Agent B will use GraphRAG tools.
        taskB = (
            f"Based on these recent findings:\n\n{contextForB}\n\n"
            f"Query the knowledge graph for historical context and relationships about Rocket Lab. "
            f"Provide additional insights that complement the above findings."
        )
        resultB = await agentB.performResearchTask(taskB)
        
        # Optionally prune Agent B's output before passing to Agent C
        contextForC = f"Web Research:\n{contextForB}\n\nKnowledge Graph Analysis:\n{resultB}"
        if use_pruning:
            from output_pruner import pruneAgentOutput
            resultB_pruned = pruneAgentOutput(resultB, agentType="graphrag")
            contextForC = f"Web Research:\n{contextForB}\n\nKnowledge Graph Analysis:\n{resultB_pruned}"
            logger.info(f"Agent B output: {len(resultB)} chars → {len(resultB_pruned)} chars (pruned)")
        else:
            logger.info(f"Agent B output: {len(resultB)} chars (raw)")
        
        # STEP 3: Agent C provides financial analysis using both A and B's findings
        logger.info(f"\n=== Agent C (Finance) - {'PRUNED' if use_pruning else 'RAW'} ===")
        taskC = (
            f"Based on this comprehensive research:\n\n{contextForC}\n\n"
            f"Get the current stock price for RKLB and provide a brief financial assessment "
            f"considering the above context."
        )
        resultC = await agentC.performResearchTask(taskC)

        # --- Verification ---
        logger.info("\n=== Verification ===")

        # 7a. Token Accounting
        totalUsage = state.usage
        logger.info(f"Total tokens: {totalUsage.total_tokens}")
        logger.info(f"Prompt: {totalUsage.prompt_tokens} | Completion: {totalUsage.completion_tokens}")
        logger.info(f"Cached: {totalUsage.cached_tokens} | Reasoning: {totalUsage.reasoning_tokens}")
        logger.info(f"Cost: ${totalUsage.cost:.6f}")
        assert totalUsage.total_tokens > 0, "FAIL: No tokens tracked"
        assert totalUsage.prompt_tokens > 0, "FAIL: No prompt tokens"
        assert totalUsage.completion_tokens > 0, "FAIL: No completion tokens"
        logger.info("✅ Token accounting verified")

        # 7b. Tool Isolation
        # Filter out THOUGHT pseudo-entries
        MONITORING_PSEUDO_TOOLS = {"THOUGHT"}
        realCallsA = [t for t in state.toolCalls if t["agentName"] == "Qualitative_Agent" and t["toolName"] not in MONITORING_PSEUDO_TOOLS]
        realCallsB = [t for t in state.toolCalls if t["agentName"] == "GraphRAG_Agent" and t["toolName"] not in MONITORING_PSEUDO_TOOLS]
        realCallsC = [t for t in state.toolCalls if t["agentName"] == "Finance_Agent" and t["toolName"] not in MONITORING_PSEUDO_TOOLS]

        logger.info(f"Agent A real tool calls: {[c['toolName'] for c in realCallsA]}")
        logger.info(f"Agent B real tool calls: {[c['toolName'] for c in realCallsB]}")
        logger.info(f"Agent C real tool calls: {[c['toolName'] for c in realCallsC]}")

        graphragToolNames = set(graphragProvider.toolsLibrary.keys())
        financeToolNames = set(financeProvider.toolsLibrary.keys())

        assert len(realCallsA) > 0, "FAIL: Agent A made no real tool calls"
        assert all(c["toolName"] == "web_search" for c in realCallsA), \
            f"FAIL: Agent A used non-web tools: {[c['toolName'] for c in realCallsA]}"

        assert len(realCallsB) > 0, "FAIL: Agent B made no real tool calls"
        for call in realCallsB:
            assert call["toolName"] != "web_search", "FAIL: Agent B used web_search!"
            assert call["toolName"] not in financeToolNames, \
                f"FAIL: Agent B used finance tool: {call['toolName']}"

        assert len(realCallsC) > 0, "FAIL: Agent C made no real tool calls"
        for call in realCallsC:
            assert call["toolName"] != "web_search", "FAIL: Agent C used web_search!"
            assert call["toolName"] not in graphragToolNames, \
                f"FAIL: Agent C used graphrag tool: {call['toolName']}"

        logger.info("✅ Tool isolation verified — each agent used ONLY its designated tools")

        # 7c. Per-agent token sum matches total
        agentTokenSum = sum(a["usage"].total_tokens for a in state.agents.values())
        logger.info(f"Per-agent token sum: {agentTokenSum} | State total: {state.totalTokens}")
        assert state.totalTokens == agentTokenSum, \
            f"FAIL: totalTokens ({state.totalTokens}) != agentSum ({agentTokenSum})"
        logger.info("✅ Token consistency verified")

        logger.info(f"\n🎉 ALL TESTS PASSED ({'PRUNED' if use_pruning else 'RAW'} mode)")
        
        return {
            "total": totalUsage.total_tokens,
            "downstream_prompt": (
                state.agents["GraphRAG_Agent"]["usage"].prompt_tokens + 
                state.agents["Finance_Agent"]["usage"].prompt_tokens
            ),
            "chars_saved": state.totalCharsSaved
        }

    except Exception as e:
        logger.error(f"Test FAILED in {'PRUNED' if use_pruning else 'RAW'} mode: {e}")
        raise


async def main():
    """Run both scenarios automatically and compare"""
    
    # 1. Suppress verbose background noise
    logging.getLogger("multi_agent_investment").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("monitoring_wrapper").setLevel(logging.WARNING)
    
    # Patch Multi-Agent once
    patch_multi_agent()

    print("=" * 80)
    print("🚀 INTEGRATION TEST: OUTPUT PRUNING IMPACT ANALYSIS")
    print("=" * 80)
    
    # --- Persistence Setup ---
    cfg.config.verifyConfiguration()
    apiKey = cfg.config.OPENROUTER_API_KEY
    testModel = cfg.config.INTEGRATION_TEST_MODEL

    llmClient = OpenRouterClient(
        apiKey=apiKey,
        baseUrl="https://openrouter.ai/api/v1/chat/completions",
        maxRetries=3
    )

    # Tool Providers
    webSearchAgent = WebSearchAgent(apiKey)
    webAdapter = InternalAgentAdapter("web-search", webSearchAgent)

    graphragProvider = McpToolProvider("graphrag", StdioServerParameters(
        command="docker",
        args=[
            "run", "-i", "--rm",
            "-v", f"{cfg.config.GRAPHRAG_PROJECT_PATH}:/app",
            "-v", f"{cfg.config.GRAPHRAG_NODE_MODULES_VOLUME}:/app/node_modules",
            "-v", f"{cfg.config.GRAPHRAG_REGISTRY_DIR}:/root/.graphrag",
            "-v", f"{cfg.config.GRAPHRAG_PROJECT_PATH}/.DuckDB:/app/.DuckDB",
            "-v", f"{cfg.config.GRAPHRAG_PROJECT_PATH}/output:/app/output",
            "--add-host=host.docker.internal:host-gateway",
            "-e", f"OPENROUTER_API_KEY={apiKey}",
            "-e", f"GRAPHRAG_DATABASE={cfg.config.GRAPHRAG_DATABASE}",
            "-e", "NODE_NO_WARNINGS=1",
            cfg.config.GRAPHRAG_IMAGE,
            "npx", "tsx", "mcp_server.ts"
        ],
        env=None
    ))

    financeProvider = McpToolProvider("finance-tools", StdioServerParameters(
        command="docker",
        args=["run", "-i", "--rm", cfg.config.FINANCE_TOOLS_IMAGE],
        env=None
    ))

    # Agent Profiles
    profileA = AgentProfile(
        name="Qualitative_Agent",
        skills=["Web Search", "Market Research"],
        personality=["Thorough", "Curious"],
        specialization="Qualitative Research",
        fullSpec=(
            "You are a Qualitative Researcher. "
            "Use the web_search tool to find recent news about the given topic. "
            "You MUST call the web_search tool exactly once, then return your findings."
        )
    )
    agentA = Agent(profileA, llmClient, model=testModel, agentAdapter=webAdapter)

    profileB = AgentProfile(
        name="GraphRAG_Agent",
        skills=["Knowledge Graph", "Pattern Recognition"],
        personality=["Analytical", "Precise"],
        specialization="Internal Data Analysis",
        fullSpec=(
            "You are a Knowledge Graph Specialist. "
            "Use the available GraphRAG tools to query the knowledge graph. "
            "Call one tool, then return your findings."
        )
    )
    agentB = Agent(profileB, llmClient, model=testModel, mcpProvider=graphragProvider)

    profileC = AgentProfile(
        name="Finance_Agent",
        skills=["Financial Analysis", "Metrics"],
        personality=["Data-driven", "Objective"],
        specialization="Quantitative Analysis",
        fullSpec=(
            "You are a Quantitative Analyst. "
            "Use the available finance tools to get current stock data. "
            "Call one tool, then return your findings."
        )
    )
    agentC = Agent(profileC, llmClient, model=testModel, mcpProvider=financeProvider)

    # Connect MCP Providers once
    logger.info("Connecting to MCP Tool Providers (Persistent Context)...")
    await graphragProvider.connect()
    await financeProvider.connect()
    logger.info(f"GraphRAG tools: {list(graphragProvider.toolsLibrary.keys())}")
    logger.info(f"Finance tools: {list(financeProvider.toolsLibrary.keys())}")

    try:
        # Scenario 1: RAW
        print("\n[1/2] Running Scenario: RAW (Full Context Handoff)...")
        raw_results = await run_test(agentA, agentB, agentC, graphragProvider, financeProvider, use_pruning=False)
        print(f"✅ RAW Mode Complete. Downstream Prompts: {raw_results['downstream_prompt']:,} tokens")
        
        # Scenario 2: PRUNED
        print("\n[2/2] Running Scenario: PRUNED (Boilerplate Stripped)...")
        # Reset some global state before second run
        state.totalCharsSaved = 0 
        pruned_results = await run_test(agentA, agentB, agentC, graphragProvider, financeProvider, use_pruning=True)
        print(f"✅ PRUNED Mode Complete. Downstream Prompts: {pruned_results['downstream_prompt']:,} tokens")
        
        # Display comparison
        print("\n" + "=" * 80)
        print("FINAL COMPARISON")
        print("=" * 80)
        
        raw_p = raw_results['downstream_prompt']
        pruned_p = pruned_results['downstream_prompt']
        
        print(f"RAW Handoff Context:     {raw_p:,} tokens")
        print(f"PRUNED Handoff Context:  {pruned_p:,} tokens")
        
        diff = raw_p - pruned_p
        if diff > 0:
            pct = (diff / raw_p) * 100
            print(f"TOKEN SAVINGS:           {diff:,} tokens ({pct:.1f}%) ✅")
        elif diff < 0:
            pct = (abs(diff) / raw_p) * 100
            print(f"TOKEN INCREASE:          {abs(diff):,} tokens ({pct:.1f}%) ⚠️ (LLM Variation)")
        else:
            print(f"Token savings:  0 (identical)")

        # Character metrics for additional transparency
        print("-" * 40)
        print(f"Total RAW/PRUNED Tokens: {raw_results['total']:,} -> {pruned_results['total']:,}")
        print(f"Total Characters Pruned: {pruned_results['chars_saved']:,}")
        print("=" * 80)
        print("\n✅ All tests passed. Verification complete.")

    finally:
        # Final cleanup
        logger.info("Cleaning up MCP Tool Providers...")
        try:
            await graphragProvider.cleanup()
            await financeProvider.cleanup()
        except:
            pass


if __name__ == "__main__":
    asyncio.run(main())
