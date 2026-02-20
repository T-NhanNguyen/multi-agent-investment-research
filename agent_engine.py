# ABOUTME: Core engine for agent management, profiling, and tool integration.
# ABOUTME: Provides specialized adapters for MCP bridges and web search capabilities.

import asyncio
import json
import logging
import httpx
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from output_pruner import pruneAgentOutput
from llm_client import ILlmClient, ChatResponse
import internal_configs as cfg
from finviz_scraper import FinvizScraper

# Configure logging
logger = logging.getLogger(__name__)

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
        self.baseUrl = cfg.config.OPENROUTER_RESPONSES_ENDPOINT
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

class FinvizAdapter:
    """
    Adapter to expose FinvizScraper as a tool for agents.
    Complies with the same execution interface as InternalAgentAdapter.
    """
    
    def __init__(self, name: str, scraper: FinvizScraper):
        self.name = name
        self.scraper = scraper
        self.toolsLibrary = cfg.FINVIZ_TOOL_DEFINITION

    async def getOpenAiToolSchema(self) -> List[Dict]:
        """Convert Finviz tool definitions to OpenAI tool call schema."""
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
        """Route tool call to the FinvizScraper."""
        if name == "get_finviz_data":
            ticker = arguments.get("ticker")
            if not ticker:
                return "Error: Missing ticker symbol."
            
            result = await self.scraper.scrapeTicker(ticker)
            if result.get("success"):
                # Return the content directly as it's intended for agent context
                return result["content"]
            else:
                return f"Error scraping Finviz for {ticker}: {result.get('error')}"
        
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
        self.lastResponse: Optional[ChatResponse] = None
    
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
                
                # Track the last response for observability
                self.lastResponse = llmResult
                
                # Log the intuitive SDK response summary
                logger.debug(f"{self.profile.name}: LLM Result Detail:\n{llmResult}")
                
                assistantMessage = llmResult.message
                
                # CASE A: Final Text Response received
                if not llmResult.toolCalls:
                    researchReportContent = llmResult.content.strip()
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
