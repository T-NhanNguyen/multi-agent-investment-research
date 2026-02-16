# ABOUTME: Core orchestrator for the Multi-Agent Investment Research System.
# ABOUTME: Manages agent lifecycles, MCP bridge connectivity, and multi-phase research workflows.


import asyncio
import json
import logging
import re
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from contextlib import AsyncExitStack
import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from output_pruner import pruneAgentOutput
import internal_configs as cfg
from llm_client import ILlmClient, getLLMClient

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
            await self.exitStack.aclose()
            self.session = None
        except asyncio.CancelledError:
            # Cleanup was cancelled during shutdown - suppress it
            logger.debug(f"Cleanup cancelled for [{self.name}] (shutdown in progress)")
            # Don't re-raise - let shutdown complete gracefully
        except Exception as exc:
            # Log but don't raise - cleanup errors during shutdown are expected
            logger.debug(f"Cleanup exception for [{self.name}]: {exc}")

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
        self.messageHistory: List[Dict[str, Any]] = []
    
    def resetHistory(self):
        """Clears the agent's conversation history for a new research session."""
        self.messageHistory = []
    
    def _buildSystemPrompt(self) -> str:
        """Constructs the system prompt from the agent's full markdown specification."""
        return self.profile.fullSpec
    
    async def performResearchTask(self, query: str) -> str:
        """
        Execute analysis task with tool-calling loop.
        Persistent history is maintained across calls unless resetHistory() is called.
        """
        # Initialize history if empty
        if not self.messageHistory:
            self.messageHistory.append({"role": "system", "content": self.profile.fullSpec})
        
        # Add new user query
        self.messageHistory.append({"role": "user", "content": query})
        
        availableTools = []
        if self.mcpProvider:
            mcpTools = await self.mcpProvider.getOpenAiToolSchema()
            availableTools.extend(mcpTools)
            
        if self.agentAdapter:
            agentTools = await self.agentAdapter.getOpenAiToolSchema()
            availableTools.extend(agentTools)
        
        
        for _ in range(cfg.config.MAX_TOOL_CYCLES):
            try:
                llmResult = await self.llmClient.chatCompletion(
                    self.model, 
                    self.messageHistory, 
                    tools=availableTools if availableTools else None
                )
                
                assistantMessage = llmResult["choices"][0]["message"]
                
                # CASE A: Final Text Response received
                if not assistantMessage.get("tool_calls"):
                    researchReportContent = assistantMessage.get("content", "").strip()
                    # Append assistant completion to history
                    self.messageHistory.append(assistantMessage)
                    
                    if not researchReportContent:
                        logger.warning(f"{self.profile.name}: LLM returned empty content. Retrying...")
                        continue

                    logger.info(f"{self.profile.name}: Analysis complete ({len(researchReportContent)} chars)")
                    return researchReportContent

                # CASE B: Tool Calls Requested by LLM
                self.messageHistory.append(assistantMessage) 
                
                for requestedTool in assistantMessage["tool_calls"]:
                    targetToolName = requestedTool["function"]["name"]
                    rawArguments = requestedTool["function"]["arguments"]
                    
                    # Parse tool arguments — feed errors back for self-correction
                    try:
                        toolArguments = json.loads(rawArguments)
                    except (json.JSONDecodeError, TypeError) as parseError:
                        logger.warning(
                            f"{self.profile.name}: Malformed tool JSON for {targetToolName}: {parseError}. "
                            f"Raw: {rawArguments[:200]}. Feeding error back for self-correction."
                        )
                        self.messageHistory.append({
                            "role": "tool",
                            "tool_call_id": requestedTool["id"],
                            "name": targetToolName,
                            "content": (
                                f"ERROR: Your tool call arguments were not valid JSON. "
                                f"Parse error: {parseError}. "
                                f"Your raw output was: {rawArguments[:300]}. "
                                f"Please re-call this tool with properly formatted JSON arguments "
                                f"(use double quotes for all keys and string values)."
                            )
                        })
                        continue
                    
                    logger.info(f"{self.profile.name}: LLM suggested tool -> {targetToolName}")
                    
                    # Route the tool call to the correct bridge
                    if self.mcpProvider and targetToolName in self.mcpProvider.toolsLibrary:
                        executionResult = await self.mcpProvider.executeMcpTool(targetToolName, toolArguments)
                    elif self.agentAdapter and targetToolName in self.agentAdapter.toolsLibrary:
                        executionResult = await self.agentAdapter.executeMcpTool(targetToolName, toolArguments)
                    else:
                        executionResult = f"Error: Tool {targetToolName} not found in this agent's bridge context."
                    
                    self.messageHistory.append({
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
        # Prune original analysis for context efficiency
        prunedAnalysis = pruneAgentOutput(originalAnalysis)
        
        clarificationPrompt = cfg.FOLLOW_UP_PROMPT_TEMPLATE.format(
            originalAnalysis=prunedAnalysis,
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

    def _parseSynthesisResponse(self, response: str) -> Dict[str, Any]:
        """
        Parse synthesis agent markdown output using regex to extract targeted requests or completion.
        """
        logger.debug(f"Parsing synthesis response: {response[:200]}...")  # First 200 chars
        # 1. Detect completion signals
        completionPatterns = [
            r"\bDone\b",
            r"\bThere is nothing else needed\b",
            r"\bI have enough information\b",
            r"\bready to provide final\b",
            r"\bno further (research|information|data) needed\b",
            r"\bsufficient (data|information|context)\b"
        ]
        isComplete = any(re.search(p, response, re.IGNORECASE) for p in completionPatterns)
        
        if isComplete:
            logger.info("Synthesis Agent signaled completion ('Done').")
            return {"status": "complete", "ready_for_final_synthesis": True}

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
        Retrieves cumulative token usage from the monitoring wrapper if available.
        """
        try:
            from monitoring_wrapper import state
            return {
                "total_tokens": state.totalTokens,
                "usage": state.usage.to_dict()
            }
        except Exception as e:
            logger.debug(f"Usage tracking unavailable: {e}")
            return {"total_tokens": 0, "usage": {}}
    
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

    async def executeResearchSession(self, investmentQuery: str) -> Dict[str, Any]:
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
        
        # Track the sequence of intelligence gathered for reporting
        intelligenceGaps = []
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
                "synthesis": {"finalRecommendation": finalReport},
                "momentum": {"analysis": momentumAnalysis}
            },
            "usage": self._getUsageSummary()
        }
        
        # Export Final Markdown Artifact
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
        """Generates and writes a formatted markdown report based on the research results."""
        creationTime = datetime.now().strftime("%Y%m%d_%H%M%S")
        outputFilepath = self.outputDir / f"research_{result['mode']}_{creationTime}.md"
        
        # Consolidate all iteration findings for the report
        cycles = result['agents'].get('research_cycles', [])
        allQual = "\n\n".join([f"### Iteration {h['iteration']}\n{h['results']['qual']}" for h in cycles])
        allQuant = "\n\n".join([f"### Iteration {h['iteration']}\n{h['results']['quant']}" for h in cycles])

        # Format core intelligence sections
        compositeReport = f"# Investment Research Report: {result['query']}\n\n"
        compositeReport += f"**Timestamp**: {result['timestamp']}\n"
        compositeReport += f"**Strategy Mode**: {result['mode']}\n\n"
        
        compositeReport += "## Qualitative Intelligence Cycle\n"
        compositeReport += allQual + "\n\n"
        
        compositeReport += "## Quantitative Data Cycle\n"
        compositeReport += allQuant + "\n\n"
        
        if result['mode'] in ['fundamental', 'all']:
            compositeReport += "## Final Investment Thesis\n"
            compositeReport += result['agents'].get('synthesis', {}).get('finalRecommendation', 'N/A') + "\n\n"
            
        if result['mode'] in ['momentum', 'all']:
            compositeReport += "## Momentum Strategy Analysis\n"
            compositeReport += result['agents'].get('momentum', {}).get('analysis', 'N/A') + "\n\n"
        
        usage = result.get("usage", {})
        if usage and usage.get("total_tokens"):
            compositeReport += "---\n### Resource Usage\n"
            compositeReport += f"Total Tokens: {usage['total_tokens']}\n"
        
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
    
    try:
        sessionData = await orchestrator.executeResearchSession(query)
        
        if "error" not in sessionData:
            print("\n=== INVESTIGATION COMPLETE ===")
            print(f"Strategy: {sessionData['mode']} | Artifact: output/research_...")
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

