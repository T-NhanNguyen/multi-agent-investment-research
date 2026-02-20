# ABOUTME: Core orchestrator for the Multi-Agent Investment Research System.
# ABOUTME: Manages agent lifecycles, MCP bridge connectivity, and multi-phase research workflows.


import asyncio
import logging
import re
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from output_pruner import pruneAgentOutput
import internal_configs as cfg
from llm_client import getLlmClient
from agent_engine import (
    Agent, 
    McpToolProvider, 
    WebSearchAgent, 
    InternalAgentAdapter, 
    AgentSpecLoader,
    FinvizAdapter
)
from mcp import StdioServerParameters
from monitoring_wrapper import patch_multi_agent
from finviz_scraper import FinvizScraper

# Environment variables are loaded automatically by internal_configs

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Configuration Constants & Defaults ---
# Using classes and constants from agent_engine.py and internal_configs.py


class ResearchOrchestrator:
    """Orchestrates the multi-agent investment research lifecycle across distributed tool providers."""
    
    # --- Workflow Configuration ---
    PHASE_THROTTLE_SECONDS = cfg.config.PHASE_THROTTLE_SECONDS
    
    def __init__(
        self, 
        agentsDir: str = None,
        modelName: str = None,
        mode: str = cfg.config.DEFAULT_RESEARCH_MODE,
        outputDirectory: str = cfg.config.OUTPUT_DIR
    ):
        self.mode = mode.lower()
        if self.mode not in cfg.config.RESEARCH_MODES:
            raise ValueError(f"Invalid mode. Must be one of {cfg.config.RESEARCH_MODES}")

        # Strict environment validation
        cfg.config.verifyConfiguration()
        self.apiKey = cfg.config.OPENROUTER_API_KEY
        
        # Initialize Shared LLM Client
        
        # Use OpenRouter for search grounding, but use factory for main logic
        self.llmClient = getLlmClient(
            provider=cfg.config.LLM_PROVIDER,
            model=cfg.config.PRIMARY_MODEL,
            apiKey=self.apiKey,
            baseUrl=None, 
            backoffCap=cfg.config.RATE_LIMIT_BACKOFF_CAP
        )
        
        # Determine absolute path for agent persona specifications
        if agentsDir is None:
            agentsDir = str(Path(__file__).parent / "agent-definition-files")
        self.agentsDir = Path(agentsDir)
        
        # Model configuration
        self.model = modelName or cfg.config.PRIMARY_MODEL
            
        self.outputDir = Path(outputDirectory)
        self.outputDir.mkdir(exist_ok=True)
        
        # Initialize specialized subdirectories for clean reporting
        self.logDir = self.outputDir / "research_logs"
        self.reportDir = self.outputDir / "human-centric_reports"
        self.logDir.mkdir(exist_ok=True)
        self.reportDir.mkdir(exist_ok=True)
        
        # GraphRAG path validation (required for Docker sibling volume mounts)
        registryPath = cfg.config.GRAPHRAG_REGISTRY_DIR
        projectHomePath = cfg.config.GRAPHRAG_PROJECT_PATH
        
        if not registryPath or not projectHomePath:
            raise ValueError("GRAPHRAG_REGISTRY_DIR or GRAPHRAG_PROJECT_PATH not set in .env")
            
        # Initialize Tool Providers
        self.toolProviders: Dict[str, McpToolProvider] = {
            "finance": McpToolProvider("finance-tools", StdioServerParameters(
                command="docker",
                args=["run", "-i", "--rm", cfg.config.FINANCE_TOOLS_IMAGE],
                env=None
            )),
            "graphrag": McpToolProvider("graphrag", StdioServerParameters(
                command="docker",
                args=[
                    "run", "-i", "--rm",
                    "-v", f"{projectHomePath}:/app",
                    "-v", f"{cfg.config.GRAPHRAG_NODE_MODULES_VOLUME}:/app/node_modules",
                    "-v", f"{registryPath}:/root/.graphrag",
                    "-v", f"{projectHomePath}/.DuckDB:/app/.DuckDB",
                    "-v", f"{projectHomePath}/output:/app/output",
                    "--add-host=host.docker.internal:host-gateway",
                    "-e", f"OPENROUTER_API_KEY={self.apiKey}",
                    "-e", f"GRAPHRAG_DATABASE={cfg.config.GRAPHRAG_DATABASE}",
                    "-e", "NODE_NO_WARNINGS=1",
                    cfg.config.GRAPHRAG_IMAGE,
                    "npx", "tsx", "mcp_server.ts"
                ],
                env=None
            ))
        }
        
        # Initialize specialized Web Search Agent
        webSearchModel = cfg.config.WEB_SEARCH_MODEL
        self.webSearchAgent = WebSearchAgent(self.apiKey, model=webSearchModel)
        self.webSearchAdapter = InternalAgentAdapter("web-search", self.webSearchAgent)
        
        # Initialize Finviz Scraper and Adapter
        self.finvizScraper = FinvizScraper()
        self.finvizAdapter = FinvizAdapter("finviz", self.finvizScraper)
        
        # Bootstrap qualitative and quantitative intelligence agents
        self.qualitativeAgent = self._initializeAgentFromSpec(
            "qualitative_agent.md", 
            mcpProvider=self.toolProviders["graphrag"],
            agentAdapter=self.webSearchAdapter
        )
        
        self.quantitativeAgent = self._initializeAgentFromSpec(
            "quantitative_agent.md", 
            mcpProvider=self.toolProviders["finance"],
            agentAdapter=self.finvizAdapter
        )
        
        self.synthesisAgent = self._initializeAgentFromSpec(
            "synthesis_agent.md",
            agentAdapter=self.webSearchAdapter
        )
        
        self.momentumAgent = self._initializeAgentFromSpec(
            "momentum_agent.md",
            agentAdapter=self.webSearchAdapter
        )
        
        logger.info(f"ResearchOrchestrator online. Mode: {self.mode} | Model: {self.model}")
    
    def _initializeAgentFromSpec(
        self, 
        filename: str, 
        mcpProvider: Optional[McpToolProvider] = None,
        agentAdapter: Optional[InternalAgentAdapter] = None
    ) -> Agent:
        """Instantiate a specialized Agent from a markdown persona specification."""
        fullPath = self.agentsDir / filename
        with open(fullPath, 'r', encoding='utf-8') as specFile:
            rawSpec = specFile.read()
        agentProfile = AgentSpecLoader.loadFromMarkdown(rawSpec)
        
        return Agent(
            agentProfile, 
            self.llmClient, 
            self.model, 
            mcpProvider, 
            agentAdapter
        )

    def _parseSynthesisResponse(self, response: str) -> Dict[str, Any]:
        """
        Parse synthesis agent markdown output using regex to extract targeted requests or completion.
        """
        # 1. Detect completion signals
        completionPatterns = [
            r"\bDone\b",
            r"\bThere is nothing else needed\b",
            r"\bI have enough information\b",
            r"\bready to provide final\b",
            r"\bno further (research|information|data) needed\b",
            r"\bsufficient (data|information|context)\b"
        ]
        isComplete = False
        directAnswer = ""
        for p in completionPatterns:
            match = re.search(p, response, re.IGNORECASE)
            if match:
                isComplete = True
                # Capture the original response as well for direct printing
                # We strip the completion trigger itself to keep it clean
                directAnswer = response.replace(match.group(0), "").strip()
                # Remove common synthesis headers if they remain
                directAnswer = re.sub(r"^##\s*Analysis\s*Status\s*", "", directAnswer, flags=re.IGNORECASE).strip()
                break
        
        if isComplete:
            logger.info("Synthesis Agent signaled completion ('Done').")
            return {
                "status": "complete", 
                "ready_for_final_synthesis": True,
                "direct_answer": directAnswer
            }

        # 2. Extract targeted requests using section headers
        # Matches content between '## For Quantitative Agent:' and next '##' or end of string
        quant_match = re.search(r"## For Quantitative Agent:([\s\S]*?)(?=##|$)", response)
        qual_match = re.search(r"## For Qualitative Agent:([\s\S]*?)(?=##|$)", response)

        quant_request = quant_match.group(1).strip() if quant_match else ""
        qual_request = qual_match.group(1).strip() if qual_match else ""

        # If we have any requests, it's an iteration
        if quant_request or qual_request:
            logger.info(f"Synthesis Agent requested more info: Quant({len(quant_request)} chars), Qual({len(qual_request)} chars)")
            return {
                "status": "requesting_information",
                "quant_request": quant_request,
                "qual_request": qual_request
            }
        
        # Fallback: if no specific structure but not complete, treat it as a broad request or error
        logger.warning(f"Synthesis response was ambiguous (len={len(response)}). Fallback to broad requests.")
        return {
            "status": "requesting_information",
            "quant_request": "Provide a comprehensive quantitative report.",
            "qual_request": "Provide a comprehensive qualitative report."
        }

    async def _executeSpecialistIteration(self, quant_request: str, qual_request: str) -> Dict[str, str]:
        """
        Executes both specialist agents in parallel with their targeted requests.
        """
        # Run in parallel
        tasks = []
        if quant_request:
            tasks.append(self.quantitativeAgent.performResearchTask(quant_request))
        else:
            tasks.append(asyncio.sleep(0, result="No request for Quantitative Agent."))

        if qual_request:
            tasks.append(self.qualitativeAgent.performResearchTask(qual_request))
        else:
            tasks.append(asyncio.sleep(0, result="No request for Qualitative Agent."))

        quant_raw, qual_raw = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle potential exceptions during parallel execution
        if isinstance(quant_raw, Exception):
            logger.error(f"Quantitative Agent failed: {quant_raw}")
            quant_raw = f"ERROR: Quantitative Agent failed to respond. {quant_raw}"
        if isinstance(qual_raw, Exception):
            logger.error(f"Qualitative Agent failed: {qual_raw}")
            qual_raw = f"ERROR: Qualitative Agent failed to respond. {qual_raw}"

        # Apply pruning for next synthesis iteration
        pruned_quant = pruneAgentOutput(quant_raw, agentType="quantitative")
        pruned_qual = pruneAgentOutput(qual_raw, agentType="qualitative")

        return {
            "quant_response": pruned_quant,
            "qual_response": pruned_qual,
            "quant_raw": quant_raw,
            "qual_raw": qual_raw
        }

    def _getUsageSummary(self) -> Dict[str, Any]:
        """
        Retrieves cumulative and per-agent token usage from the monitoring wrapper.
        """
        try:
            from monitoring_wrapper import state
            agentStats = {}
            for agentName, agentData in state.agents.items():
                if "usage" in agentData and agentData["usage"].total_tokens > 0:
                    agentStats[agentName] = agentData["usage"].to_dict()
            
            return {
                "total_tokens": state.totalTokens,
                "usage": state.usage.to_dict(),
                "agents": agentStats
            }
        except Exception as e:
            logger.debug(f"Usage tracking unavailable: {e}")
            return {"total_tokens": 0, "usage": {}, "agents": {}}
    
    async def cleanup(self):
        """Teardown of all active mcp tool providers."""
        for provider in self.toolProviders.values():
            await provider.cleanup()

    async def connectAll(self):
        """
        Pre-connects all tool providers in the current task context.
        This ensures all MCP context managers are entered in the same task
        that will eventually call cleanup(), preventing task boundary errors.
        """
        logger.info("Pre-connecting all MCP Tool Providers...")
        for name, provider in self.toolProviders.items():
            try:
                if not provider.session:  # Only connect if not already connected
                    await provider.connect()
                    logger.info(f"  ✓ Connected: {name}")
            except asyncio.CancelledError:
                # Connection was cancelled - re-raise to propagate
                raise
            except Exception as e:
                # Log connection errors but continue with other providers
                logger.error(f"  ✗ Failed to connect {name}: {e}")
        logger.info("All MCP Tool Providers ready.")

    async def executeResearchSession(self, investmentQuery: str, exportReport: bool = True) -> Dict[str, Any]:
        """
        Main research workflow using the synthesis-driven iterative approach.
        Leverages persistent agent state to reduce context redundancy.
        """
        # 0. Pre-connect all providers in the MAIN task context to avoid anyio task boundary issues
        await self.connectAll()

        # 1. Reset all agent histories for a clean session
        self.synthesisAgent.resetHistory()
        self.qualitativeAgent.resetHistory()
        self.quantitativeAgent.resetHistory()
        self.momentumAgent.resetHistory()

        logger.info(f"Starting research session: '{investmentQuery}'")
        
        # 2. Iteration 0: Synthesis agent analyzes query and requests broad context
        initialPrompt = cfg.SYNTHESIS_INITIAL_PROMPT_TEMPLATE.format(investmentQuery=investmentQuery)
        synthesisRaw = await self.synthesisAgent.performResearchTask(initialPrompt)
        
        synthesisAction = self._parseSynthesisResponse(synthesisRaw)
        
        # If quick mode is on, we skip logging/reporting to files
        if self.mode == 'quick':
            exportReport = False
        
        # Track the sequence of intelligence gathered for reporting
        researchCycles = []
        
        iteration = 1
        maxIterations = cfg.config.MAX_SYNTHESIS_ITERATIONS
        
        # 3. Research Loop: Specialists gathering and Synthesis refinement
        while synthesisAction["status"] == "requesting_information" and iteration <= maxIterations:
            logger.info(f"--- RESEARCH ITERATION {iteration}/{maxIterations} ---")
            
            # Execute specialists (Qual/Quant) in parallel
            specialistResults = await self._executeSpecialistIteration(
                synthesisAction.get("quant_request", ""),
                synthesisAction.get("qual_request", "")
            )
            
            # Record cycle
            researchCycles.append({
                "iteration": iteration,
                "requests": {
                    "quant": synthesisAction.get("quant_request"),
                    "qual": synthesisAction.get("qual_request")
                },
                "results": {
                    "quant": specialistResults["quant_response"],
                    "qual": specialistResults["qual_response"]
                }
            })
            
            # 4. Feedback to Synthesis Agent
            # Since the agent is stateful, we only need to provide the NEW responses
            iterationFeedback = f"""
                Specialist Responses (Iteration {iteration}):

                ## Qualitative Analysis:
                {specialistResults['qual_response']}

                ## Quantitative Analysis:
                {specialistResults['quant_response']}

                ---
                Evaluate these results. If significant gaps remain, request targeted follow-ups (Iterations left: {maxIterations - iteration}). 
                If you have enough information for a final thesis, simply output "Done".
                """
            synthesisRaw = await self.synthesisAgent.performResearchTask(iterationFeedback)
            synthesisAction = self._parseSynthesisResponse(synthesisRaw)
            
            iteration += 1

        # 5. Final Synthesis Phase
        finalReport = ""
        if self.mode in ["fundamental", "all"]:
            finalReport = await self.phase_FundamentalFinalization(investmentQuery)
        
        momentumAnalysis = ""
        if self.mode in ["momentum", "all"]:
            momentumAnalysis = await self.phase_MomentumFinalization(investmentQuery)

        # Final Session Output
        sessionResult = {
            "query": investmentQuery,
            "timestamp": datetime.now().isoformat(),
            "mode": self.mode,
            "agents": {
                "research_cycles": researchCycles,
                "synthesis": {
                    "finalRecommendation": finalReport,
                    "direct_answer": synthesisAction.get("direct_answer", "")
                },
                "momentum": {"analysis": momentumAnalysis}
            },
            "usage": self._getUsageSummary()
        }
        
        # Export Final Markdown Artifact
        if exportReport:
            self.exportResearchReport(sessionResult)
        return sessionResult

    async def phase_FundamentalFinalization(self, query: str) -> str:
        """
        Triggers final synthesis Mode 3 after research iterations are complete.
        Leverages synthesis agent's persistent history.
        """
        logger.info("Finalizing Fundamental Analysis (Mode 3 Synthesis)")
        
        finalPrompt = cfg.SYNTHESIS_FINAL_THESIS_TEMPLATE.format(investmentQuery=query)
        return await self.synthesisAgent.performResearchTask(finalPrompt)

    async def phase_MomentumFinalization(self, query: str) -> str:
        """
        Triggers momentum finalization. 
        Note: Momentum agent currently leverages context via synthesis results if needed.
        """
        logger.info(f"Finalizing Momentum Analysis for '{query}'")
        
        # Momentum agent performs its specialized styling/analysis on its persistent context
        return await self.momentumAgent.performResearchTask(f"Finalize momentum thesis for: {query}")

    # --- Utility Methods ---

    async def _runAgentTask(self, agent: Agent, task: str) -> str:
        """Raw agent task execution."""
        return await agent.performResearchTask(task)

    def exportResearchReport(self, result: Dict):
        """
        Generates and writes two separate reports:
        1. Human-Centric Report: Clean synthesis output following the Writing Guide.
        2. Process Log: Transparent audit trail of all agent iterations and specialist results.
        """
        creationTime = datetime.now().strftime("%Y%m%d_%H%M%S")
        safeQuery = re.sub(r'[^\w\s-]', '', result['query']).replace(' ', '_')[:30]
        baseName = f"{result['mode']}_{safeQuery}_{creationTime}.md"
        
        logPath = self.logDir / baseName
        reportPath = self.reportDir / baseName

        # --- 1. Generate Process Log ---
        cycles = result['agents'].get('research_cycles', [])
        auditTrail = ""
        for h in cycles:
            auditTrail += f"### Iteration {h['iteration']}\n"
            auditTrail += f"#### Quantitative Agent Request:\n> {h['requests']['quant']}\n\n"
            auditTrail += f"#### Qualitative Agent Request:\n> {h['requests']['qual']}\n\n"
            auditTrail += f"#### Quantitative Response:\n{h['results']['quant']}\n\n"
            auditTrail += f"#### Qualitative Response:\n{h['results']['qual']}\n\n"
            auditTrail += "---\n\n"

        usage = result.get("usage", {})
        usageStr = f"Total Tokens: {usage.get('total_tokens', 0)}"

        processLog = cfg.LOG_REPORT_TEMPLATE.format(
            query=result['query'],
            timestamp=result['timestamp'],
            mode=result['mode'],
            cycles=auditTrail,
            usage=usageStr
        )
        
        if result['mode'] in ['momentum', 'all']:
            momentumOut = result['agents'].get('momentum', {}).get('analysis', 'N/A')
            processLog += cfg.MOMENTUM_REPORT_SECTION.format(momentumAnalysis=momentumOut)

        # --- 2. Generate Human-Centric Report ---
        # This is primarily the raw output from the Synthesis Agent (Mode 3)
        humanReport = result['agents'].get('synthesis', {}).get('finalRecommendation', '')
        
        # If finalRecommendation is empty (e.g. Iteration 0 complete), look for direct answer
        if not humanReport:
            # Try to grab the last synthesis response before "Done" if it was a direct answer
            humanReport = result['agents'].get('synthesis', {}).get('direct_answer', '')

        if result['mode'] == 'momentum':
            humanReport = result['agents'].get('momentum', {}).get('analysis', '')
        elif result['mode'] == 'all' and result['agents'].get('momentum', {}).get('analysis'):
            # Only append if the synthesis hasn't already integrated it
            if "Momentum Strategy Analysis" not in humanReport:
                humanReport += "\n\n---\n## Momentum Intelligence Addendum\n\n"
                humanReport += result['agents'].get('momentum', {}).get('analysis', '')

        # Write both files
        with open(logPath, 'w', encoding='utf-8') as logFile:
            logFile.write(processLog)
        
        with open(reportPath, 'w', encoding='utf-8') as reportFile:
            reportFile.write(humanReport)

        logger.info(f"Research Audit Log: {logPath}")
        logger.info(f"Human-Centric Report: {reportPath}")

async def main():
    # Patch for monitoring when running CLI directly
    try:
        patch_multi_agent()
    except ImportError:
        pass

    try:
        cfg.config.verifyConfiguration()
    except ValueError as e:
        print(e)
        return
        
    query = input(f"Enter target query [{cfg.config.DEFAULT_INVESTMENT_QUERY}]: ").strip() or cfg.config.DEFAULT_INVESTMENT_QUERY
    
    print("\nSelect Investigation Strategy:")
    print("1. Fundamental Strategy (Comprehensive Research)")
    print("2. Momentum Strategy (Technical/Flow Focus)")
    print("3. Hybrid Strategy (All Specialist Agents)")
    print("0. Quick Strategy (Direct Answer, No Files)")
    choice = input("\nSelect Strategy [1-3, 0 for Quick]: ").strip()
    
    modeMap = {"1": "fundamental", "2": "momentum", "3": "all", "0": "quick"}
    mode = modeMap.get(choice, "fundamental")
    
    orchestrator = ResearchOrchestrator(mode=mode)
    
    try:
        sessionData = await orchestrator.executeResearchSession(query)
        
        if "error" not in sessionData:
            print("\n=== INVESTIGATION COMPLETE ===")
            
            # Print direct answer if available (for Quick mode or early completion)
            synthesisData = sessionData.get("agents", {}).get("synthesis", {})
            directAnswer = synthesisData.get("direct_answer")
            finalRec = synthesisData.get("finalRecommendation")
            
            if directAnswer:
                print("\n--- DIRECT ANSWER ---")
                print(directAnswer)
                print("---------------------\n")
            
            if sessionData['mode'] == 'quick':
                print(f"Strategy: Quick | Response delivered via CLI")
            else:
                print(f"Strategy: {sessionData['mode']} | Artifact: output/research_...")
            
            # Print Token Statistics
            usage = sessionData.get("usage", {})
            if usage and usage.get("total_tokens", 0) > 0:
                print("\n--- TOKEN CONSUMPTION SUMMARY ---")
                print(f"Total Tokens: {usage['total_tokens']:,}")
                
                if "agents" in usage and usage["agents"]:
                    print("\nPer-Agent Statistics:")
                    for agent, stats in usage["agents"].items():
                        print(f"  - {agent:25} : {stats['total_tokens']:,} tokens")
                print("---------------------------------\n")
        else:
            print(f"\nInvestigation Fault: {sessionData['error']}")

    finally:
        # Explicit cleanup in the same async context
        logger.info("Cleaning up orchestrator resources...")
        try:
            await orchestrator.cleanup()
        except asyncio.CancelledError:
            logger.debug("Cleanup cancelled during shutdown")
        except Exception as e:
            logger.debug(f"Cleanup error: {e}")
        
        # Give Docker containers time to terminate gracefully
        try:
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass  # Sleep was cancelled - that's fine, we're shutting down anyway


if __name__ == "__main__":
    asyncio.run(main())

