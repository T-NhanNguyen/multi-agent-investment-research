# ABOUTME: Core orchestrator for the Multi-Agent Investment Research System.
# ABOUTME: Manages agent lifecycles, MCP bridge connectivity, and multi-phase research workflows.


import os
import asyncio
import json
import logging
import re
import ast
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from contextlib import AsyncExitStack
import httpx
import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import internal_configs as cfg
from llm_client import OpenRouterClient, ILlmClient, getLLMClient

# Environment variables are loaded automatically by internal_configs

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Configuration Constants & Defaults ---
# API Endpoints
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_CHAT_ENDPOINT = f"{OPENROUTER_BASE_URL}/chat/completions"
OPENROUTER_RESPONSES_ENDPOINT = f"{OPENROUTER_BASE_URL}/responses"



@dataclass
class AgentProfile:
    """Hybrid agent profile with metadata and full specification"""
    name: str
    skills: List[str]
    personality: List[str]
    specialization: str
    fullSpec: str  # Complete markdown content as system prompt


@dataclass
class ResearchResult:
    """Container for agent research results"""
    agentName: str
    analysis: str
    timestamp: datetime
    error: Optional[str] = None


class McpToolProvider:
    """Bridges OpenRouter API with Local Docker MCP Servers to provide specialized toolsets."""
    
    def __init__(self, name: str, serverParams: StdioServerParameters):
        self.name = name
        self.serverParams = serverParams
        self.session: Optional[ClientSession] = None
        self.exitStack = AsyncExitStack()
        self.toolsLibrary = {}  # Cache tool definitions

    async def connect(self):
        """Establishes deterministic stdio connection to the Dockerized MCP host."""
        if self.session:
            return

        logger.info(f"Connecting to McpToolProvider [{self.name}]: {self.serverParams.command} {' '.join(self.serverParams.args)}...")
        
        try:
            # Start the stdio transport
            transport = await self.exitStack.enter_async_context(
                stdio_client(self.serverParams)
            )
            self.read, self.write = transport
            
            # Start the MCP session
            self.session = await self.exitStack.enter_async_context(
                ClientSession(self.read, self.write)
            )
            await self.session.initialize()
            
            # Fetch available tools and cache them
            result = await self.session.list_tools()
            self.toolsLibrary = {tool.name: tool for tool in result.tools}
            logger.info(f"Connected to [{self.name}]. Loaded {len(self.toolsLibrary)} tools.")
        except Exception as exc:
            logger.error(f"Failed to connect to McpToolProvider [{self.name}]: {exc}")
            raise

    async def getOpenAiToolSchema(self) -> List[Dict]:
        """Convert MCP tool definitions to OpenRouter/OpenAI tool call schema."""
        if not self.session:
            await self.connect()
            
        toolSchemas = []
        for tool in self.toolsLibrary.values():
            toolSchemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema  # MCP inputSchema maps 1:1 to OpenAI parameters
                }
            })
        return toolSchemas

    async def executeMcpTool(self, name: str, arguments: Dict) -> str:
        """Execute the requested tool on the Docker container and return structured text results."""
        if not self.session:
            raise RuntimeError(f"McpToolProvider Session [{self.name}] not connected")
            
        logger.info(f"Executing MCP Tool [{self.name}]: {name}({json.dumps(arguments)})")
        try:
            result = await self.session.call_tool(name, arguments)
            # Standard MCP result extraction
            if hasattr(result, 'content') and result.content:
                return result.content[0].text
            return str(result)
        except Exception as exc:
            logger.error(f"Error calling tool {name} on {self.name}: {exc}")
            return f"Error: {str(exc)}"

    async def cleanup(self):
        """Standard teardown for all active session resources."""
        logger.info(f"Cleaning up McpToolProvider [{self.name}]")
        try:
            # Shield the cleanup to prevent it from being cancelled while running
            with anyio.CancelScope(shield=True):
                await self.exitStack.aclose()
        except Exception as exc:
            # We catch everything during cleanup to ensure we don't crash during shutdown
            logger.debug(f"Interruption or error during cleanup of [{self.name}]: {exc}")


class WebSearchAgent:
    """Specialized agent using OpenRouter Responses API for web search with task-safe caching"""
    
    def __init__(self, apiKey: str, model: str = cfg.config.WEB_SEARCH_MODEL):
        self.apiKey = apiKey
        self.model = model
        self.baseUrl = OPENROUTER_RESPONSES_ENDPOINT
        self.searchCache = {}  # Semantic cache to avoid redundant web hits
        self.cacheLock = asyncio.Lock()
        
    async def search(self, query: str, maxResults: int = 3) -> str:
        """
        Execute web search via OpenRouter Responses API.
        Implements single-flight pattern via lock to prevent redundant concurrent searches.
        """
        # Normalize query for caching
        cacheKey = query.strip().lower()
        
        async with self.cacheLock:
            if cacheKey in self.searchCache:
                logger.info(f"WebSearchAgent: Serving cached result for query: '{query}'")
                return self.searchCache[cacheKey]
                
            logger.info(f"WebSearchAgent: Performing live web search for: '{query}'")
            
            payload = {
                "model": self.model,
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": query
                            }
                        ]
                    }
                ],
                "plugins": [{"id": "web", "max_results": maxResults}]
            }
            
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    response = await client.post(
                        self.baseUrl,
                        headers={
                            "Authorization": f"Bearer {self.apiKey}",
                            "Content-Type": "application/json",
                        },
                        json=payload
                    )
                    response.raise_for_status()
                    result = response.json()
                    
                    # Extract content from Responses API output
                    outputContent = ""
                    if "output" in result and result["output"]:
                        for outputItem in result["output"]:
                            # Skip reasoning/encrypted items, look for message types
                            if outputItem.get("type") == "message":
                                contentList = outputItem.get("content", [])
                                for part in contentList:
                                    partType = part.get("type")
                                    if partType in ["text", "output_text"]:
                                        outputContent += part.get("text", "")
                            
                    finalResult = outputContent.strip() or "No information found on the web for this query."
                    self.searchCache[cacheKey] = finalResult
                    return finalResult
                    
            except Exception as exc:
                logger.error(f"WebSearchAgent: API failure: {exc}")
                return f"Error performing web search: {str(exc)}"


class InternalAgentAdapter:
    """
    Adapter to expose an internal specialized agent as a callable tool for other agents.
    Mimics McpToolProvider interface for seamless integration within research loops.
    """
    
    def __init__(self, name: str, webAgent: WebSearchAgent):
        self.name = name
        self.webAgent = webAgent
        self.toolsLibrary = cfg.WEB_SEARCH_TOOL_DEFINITION

    async def getOpenAiToolSchema(self) -> List[Dict]:
        """Convert internal tool definitions to OpenAI tool call schema."""
        toolSchemas = []
        for tool in self.toolsLibrary.values():
            toolSchemas.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["inputSchema"]
                }
            })
        return toolSchemas

    async def executeMcpTool(self, name: str, arguments: Dict) -> str:
        """Route tool call to the internal WebSearchAgent."""
        if name == "web_search":
            query = arguments.get("query")
            maxResults = arguments.get("max_results", 3)
            if not query:
                return "Error: Missing search query."
            return await self.webAgent.search(query, maxResults)
        return f"Error: Tool {name} not supported by this adapter."


class Agent:
    """Investment research agent with hybrid profile and MCP tool calling capability."""
    
    def __init__(
        self, 
        profile: AgentProfile, 
        llmClient: ILlmClient,
        model: str = cfg.config.PRIMARY_MODEL,
        mcpProvider: Optional[McpToolProvider] = None,
        agentAdapter: Optional[InternalAgentAdapter] = None
    ):
        self.profile = profile
        self.llmClient = llmClient
        self.model = model
        self.mcpProvider = mcpProvider
        self.agentAdapter = agentAdapter
    
    def _buildSystemPrompt(self) -> str:
        """Constructs the system prompt from the agent's full markdown specification."""
        return self.profile.fullSpec
    
    async def performResearchTask(self, query: str) -> str:
        """
        Execute analysis task with tool-calling loop.
        Adheres to agentic focus with deterministic tool execution.
        """
        interactionHistory = [
            {"role": "system", "content": self.profile.fullSpec},
            {"role": "user", "content": query}
        ]
        
        availableTools = []
        if self.mcpProvider:
            mcpTools = await self.mcpProvider.getOpenAiToolSchema()
            availableTools.extend(mcpTools)
            
        if self.agentAdapter:
            agentTools = await self.agentAdapter.getOpenAiToolSchema()
            availableTools.extend(agentTools)
        
        toolIterationCount = 0
        MAX_TOOL_CYCLES = 10 
        
        for _ in range(MAX_TOOL_CYCLES):
            try:
                # Delegate net call to injected client
                # Client handles retries and rate limits
                llmResult = await self.llmClient.chatCompletion(
                    self.model, 
                    interactionHistory, 
                    tools=availableTools if availableTools else None
                )
                
                assistantMessage = llmResult["choices"][0]["message"]
                
                # CASE A: Final Text Response received
                if not assistantMessage.get("tool_calls"):
                    researchReportContent = assistantMessage["content"]
                    logger.info(f"{self.profile.name}: Analysis complete ({len(researchReportContent or '')} chars)")
                    return researchReportContent or "No content returned."

                # CASE B: Tool Calls Requested by LLM
                toolIterationCount += 1
                interactionHistory.append(assistantMessage) 
                
                for requestedTool in assistantMessage["tool_calls"]:
                    targetToolName = requestedTool["function"]["name"]
                    toolArguments = json.loads(requestedTool["function"]["arguments"])
                    
                    logger.info(f"{self.profile.name}: LLM suggested tool -> {targetToolName}")
                    
                    # Route the tool call to the correct bridge
                    if self.mcpProvider and targetToolName in self.mcpProvider.toolsLibrary:
                        executionResult = await self.mcpProvider.executeMcpTool(targetToolName, toolArguments)
                    elif self.agentAdapter and targetToolName in self.agentAdapter.toolsLibrary:
                        executionResult = await self.agentAdapter.executeMcpTool(targetToolName, toolArguments)
                    else:
                        executionResult = f"Error: Tool {targetToolName} not found in this agent's bridge context."
                    
                    interactionHistory.append({
                        "role": "tool",
                        "tool_call_id": requestedTool["id"],
                        "name": targetToolName,
                        "content": executionResult
                    })
                
            except Exception as e:
                logger.error(f"{self.profile.name}: Critical Agent Error: {e}")
                raise e
        
        raise RuntimeError(f"{self.profile.name}: Exceeded maximum tool iteration cycles.")

    async def provideRecursiveAnalysis(self, question: str, originalAnalysis: str) -> str:
        """
        Answer follow-up clarification questions from synthesis agent during recursive refinement.
        """
        clarificationPrompt = cfg.FOLLOW_UP_PROMPT_TEMPLATE.format(
            originalAnalysis=originalAnalysis,
            question=question,
            specialization=self.profile.specialization
        )
        return await self.performResearchTask(clarificationPrompt)


class AgentSpecLoader:
    """Loads agent persona specifications from markdown definition files."""
    
    @staticmethod
    def loadFromMarkdown(content: str) -> AgentProfile:
        """
        Parse the hybrid markdown structure to extract metadata and system prompt.
        """
        lines = content.split('\n')
        name, skills, personality, specialization = "", [], [], ""
        current_section = None
        
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('# ') and not name:
                name = stripped[2:].strip()
            elif stripped.startswith('## Skills'):
                current_section = 'skills'
            elif stripped.startswith('## Personality'):
                current_section = 'personality'
            elif stripped.startswith('## Specialization'):
                current_section = 'specialization'
            elif stripped.startswith('##'):
                current_section = None
            elif stripped.startswith('- ') and current_section in ['skills', 'personality']:
                if current_section == 'skills':
                    skills.append(stripped[2:].strip())
                else:
                    personality.append(stripped[2:].strip())
            elif stripped and current_section == 'specialization' and not stripped.startswith('#'):
                specialization = stripped
                current_section = None
        
        if not name:
            raise ValueError("Agent definition must have a name (# Header)")
        
        return AgentProfile(name, skills, personality, specialization, content)


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
        self.llmClient = getLLMClient(
            provider=cfg.config.LLM_PROVIDER,
            model=cfg.config.PRIMARY_MODEL,
            apiKey=self.apiKey,
            baseUrl=cfg.config.LOCAL_LLM_URL if cfg.config.LLM_PROVIDER == "local" else OPENROUTER_CHAT_ENDPOINT,
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
        
        # Bootstrap qualitative and quantitative intelligence agents
        self.qualitativeAgent = self._initializeAgentFromSpec(
            "qualitative_agent.md", 
            mcpProvider=self.toolProviders["graphrag"],
            agentAdapter=self.webSearchAdapter
        )
        
        self.quantitativeAgent = self._initializeAgentFromSpec(
            "quantitative_agent.md", 
            mcpProvider=self.toolProviders["finance"]
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
    
    async def cleanup(self):
        """Teardown of all active mcp tool providers."""
        for provider in self.toolProviders.values():
            await provider.cleanup()

    async def executeResearchSession(self, investmentQuery: str) -> Dict:
        """
        Executes the full multi-agent research workflow via modular phase methods.
        """
        logger.info(f"\n[RESEARCH QUERY] {investmentQuery}\n")
        
        try:
            # Standby verification for tool providers
            for providerName, provider in self.toolProviders.items():
                try:
                    await provider.connect()
                except Exception as connectionErr:
                    logger.warning(f"Standby failure for Tool Provider [{providerName}]: {connectionErr}")

            # Define State Map
            researchStateMap = {
                "qualitative": {"analysis": "", "clarification": ""},
                "quantitative": {"analysis": "", "clarification": ""},
                "synthesis": {},
                "momentum": {}
            }

            # Phase 1: Parallel Specialized Intelligence Analysis
            # ------------------------------------------------------------------
            qualResults, quantResults = await self.phase1_ParallelAnalysis(investmentQuery)
            
            researchStateMap["qualitative"]["analysis"] = qualResults.analysis
            researchStateMap["quantitative"]["analysis"] = quantResults.analysis
            
            if qualResults.error or quantResults.error:
                 return {"error": f"Phase 1 Failure: Qual({qualResults.error}) Quant({quantResults.error})"}
            
            await anyio.sleep(self.PHASE_THROTTLE_SECONDS)

            # --- Fundamental Research Track ---
            if self.mode in ["fundamental", "all"]:
                
                # Phase 2: Synthesis
                # ------------------------------------------------------------------
                initialSynthesis = await self.phase2_Synthesis(qualResults.analysis, quantResults.analysis)
                researchStateMap["synthesis"]["initialSynthesis"] = initialSynthesis
                await anyio.sleep(self.PHASE_THROTTLE_SECONDS)

                # Phase 3: Clarification
                # ------------------------------------------------------------------
                qualClar, quantClar = await self.phase3_Clarification(
                    qualResults.analysis, 
                    quantResults.analysis
                )
                researchStateMap["qualitative"]["clarification"] = qualClar
                researchStateMap["quantitative"]["clarification"] = quantClar
                
                await anyio.sleep(self.PHASE_THROTTLE_SECONDS)

                # Phase 4: Final Consolidation
                # ------------------------------------------------------------------
                finalThesis = await self.phase4_Consolidation(
                    initialSynthesis, 
                    qualClar, 
                    quantClar,
                    qualAnalysis=qualResults.analysis,
                    quantAnalysis=quantResults.analysis
                )
                researchStateMap["synthesis"]["finalRecommendation"] = finalThesis

            # --- Momentum Strategy Track ---
            if self.mode in ["momentum", "all"]:
                momentumThesis = await self.phase_MomentumStyling(
                    qualResults.analysis,
                    quantResults.analysis,
                    researchStateMap["qualitative"]["clarification"],
                    researchStateMap["quantitative"]["clarification"]
                )
                researchStateMap["momentum"]["analysis"] = momentumThesis

            # Final Session Output
            sessionResult = {
                "query": investmentQuery,
                "timestamp": datetime.now().isoformat(),
                "mode": self.mode,
                "agents": researchStateMap
            }
            
            # Export Final Markdown Artifact
            self.exportResearchReport(sessionResult)
            return sessionResult

        except Exception as exc:
            logger.error(f"Research Session failed: {exc}", exc_info=True)
            return {"error": str(exc)}
        finally:
            await self.cleanup()

    # --- Modular Phase Methods ---

    async def phase1_ParallelAnalysis(self, query: str) -> (ResearchResult, ResearchResult):
        """Execute Phase 1: Parallel Specialized Intelligence (Qual/Quant)."""
        logger.info("PHASE 1: Execution started (Qual/Quant agents)...")
        intelligenceSnapshots = {}
        
        async with anyio.create_task_group() as taskGroup:
            async def _runQualitativeBranch():
                intelligenceSnapshots['qual'] = await self._executeAgentTaskWithSafety(self.qualitativeAgent, query)
            async def _runQuantitativeBranch():
                intelligenceSnapshots['quant'] = await self._executeAgentTaskWithSafety(self.quantitativeAgent, query)
            
            taskGroup.start_soon(_runQualitativeBranch)
            taskGroup.start_soon(_runQuantitativeBranch)
            
        return intelligenceSnapshots['qual'], intelligenceSnapshots['quant']

    async def phase2_Synthesis(self, qualAnalysis: str, quantAnalysis: str) -> str:
        """Execute Phase 2: Initial Intelligence Synthesis."""
        logger.info(f"PHASE 2: Collaborative analysis initiated...")
        synthesisInput = cfg.SYNTHESIS_INPUT_TEMPLATE.format(
            qualAnalysis=qualAnalysis,
            quantAnalysis=quantAnalysis
        )
        return await self.synthesisAgent.performResearchTask(synthesisInput)

    async def phase3_Clarification(self, qualAnalysis: str, quantAnalysis: str) -> (str, str):
        """Execute Phase 3: Recursive Cross-Verification."""
        logger.info("PHASE 3 (Fundamental): Initiating recursive cross-verification...")
        qualTask = self.qualitativeAgent.provideRecursiveAnalysis(cfg.QUAL_RECURSIVE_QUESTION, qualAnalysis)
        quantTask = self.quantitativeAgent.provideRecursiveAnalysis(cfg.QUANT_RECURSIVE_QUESTION, quantAnalysis)
        
        results = await asyncio.gather(qualTask, quantTask)
        return results[0], results[1]

    def _prepareIntelligenceContext(
        self, 
        qualAnalysis: str = "N/A", 
        quantAnalysis: str = "N/A", 
        qualClar: str = "N/A", 
        quantClar: str = "N/A", 
        initialSynthesis: str = "N/A"
    ) -> str:
        """Helper to consolidate various intelligence strands into a single prompt context."""
        return cfg.AGENTS_INFORMATION_CONTEXT_TEMPLATE.format(
            qualAnalysis=qualAnalysis or "N/A",
            quantAnalysis=quantAnalysis or "N/A",
            qualClarification=qualClar or "N/A",
            quantClarification=quantClar or "N/A",
            initialSynthesis=initialSynthesis or "N/A"
        )
        
    async def phase4_Consolidation(
        self, 
        initialSynthesis: str, 
        qualClarification: str, 
        quantClarification: str,
        qualAnalysis: str = "N/A",
        quantAnalysis: str = "N/A"
    ) -> str:
        """Execute Phase 4: Final Investment Thesis Consolidation."""
        logger.info("PHASE 4 (Fundamental): Finalizing unified investment thesis...")
        
        consolidationInput = self._prepareIntelligenceContext(
            qualAnalysis=qualAnalysis,
            quantAnalysis=quantAnalysis,
            qualClar=qualClarification,
            quantClar=quantClarification,
            initialSynthesis=initialSynthesis
        )
        
        return await self.synthesisAgent.performResearchTask(consolidationInput)

    async def phase_MomentumStyling(
        self, 
        qualAnalysis: str, 
        quantAnalysis: str, 
        qualClar: str, 
        quantClar: str
    ) -> str:
        """Execute Momentum Analysis Phase using consolidated intelligence."""
        logger.info("PHASE 2b (Momentum): Generating reactive swing trade profile...")
        
        momentumInput = self._prepareIntelligenceContext(
            qualAnalysis=qualAnalysis,
            quantAnalysis=quantAnalysis,
            qualClar=qualClar,
            quantClar=quantClar,
            initialSynthesis="N/A" # Momentum agent does not consume initial synthesis typically
        )
        
        return await self.momentumAgent.performResearchTask(momentumInput)


    async def _runAgentTask(self, agent: Agent, task: str) -> str:
        """Raw agent task execution, serving as a clean entry point for unit tests."""
        return await agent.performResearchTask(task)

    async def _executeAgentTaskWithSafety(self, agent: Agent, task: str) -> ResearchResult:
        """Shielded agent execution with persistent error handling and structured result wrapping."""
        try:
            analysisOutput = await self._runAgentTask(agent, task)
            return ResearchResult(agent.profile.name, analysisOutput, datetime.now())
        except Exception as invocationError:
            logger.error(f"Agent [{agent.profile.name}] execution fault: {invocationError}")
            return ResearchResult(agent.profile.name, "", datetime.now(), str(invocationError))

    def exportResearchReport(self, result: Dict):
        """Generates and writes a formatted markdown report based on the research results."""
        creationTime = datetime.now().strftime("%Y%m%d_%H%M%S")
        outputFilepath = self.outputDir / f"research_{result['mode']}_{creationTime}.md"
        
        # Format core intelligence sections
        compositeReport = cfg.MARKDOWN_REPORT_TEMPLATE.format(
            query=result['query'],
            qualAnalysis=result['agents']['qualitative']['analysis'],
            qualClarification=result['agents']['qualitative']['clarification'],
            quantAnalysis=result['agents']['quantitative']['analysis'],
            quantClarification=result['agents']['quantitative']['clarification'],
            finalRecommendation=result['agents'].get('synthesis', {}).get('finalRecommendation', 'N/A (Momentum-only Mode)')
        )
        
        # Inject Momentum Insights if applicable
        if result['mode'] in ['momentum', 'all']:
            momentumIntelligence = cfg.MOMENTUM_REPORT_SECTION.format(
                momentumAnalysis=result['agents']['momentum']['analysis']
            )
            compositeReport += momentumIntelligence
        
        with open(outputFilepath, 'w', encoding='utf-8') as artifact:
            artifact.write(compositeReport)
        logger.info(f"Research artifact exported to {outputFilepath}")


async def main():
    try:
        cfg.config.verifyConfiguration()
    except ValueError as e:
        print(e)
        return
        
    query = input(f"Enter target query [{cfg.config.DEFAULT_INVESTMENT_QUERY}]: ").strip() or cfg.config.DEFAULT_INVESTMENT_QUERY
    
    print("\nSelect Investigation Strategy:")
    print("1. Fundamental (Long-term strategic synthesis)")
    print("2. Momentum (Reactive swing setup identification)")
    print("3. Comprehensive (Full intelligence cycle)")
    strategyInput = input("Choice [3]: ").strip()
    
    strategyMap = {"1": "fundamental", "2": "momentum", "3": "all"}
    selectedStrategy = strategyMap.get(strategyInput, "all")
    
    orchestrator = ResearchOrchestrator(mode=selectedStrategy)
    sessionData = await orchestrator.executeResearchSession(query)
    
    if "error" not in sessionData:
        print("\n=== INVESTIGATION COMPLETE ===")
        print(f"Strategy: {sessionData['mode']} | Artifact: output/research_...")
    else:
        print(f"\nInvestigation Fault: {sessionData['error']}")

if __name__ == "__main__":
    anyio.run(main)

