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
    full_spec: str  # Complete markdown content as system prompt


@dataclass
class ResearchResult:
    """Container for agent research results"""
    agent_name: str
    analysis: str
    timestamp: datetime
    error: Optional[str] = None


class MCPBridge:
    """Bridges OpenRouter API with Local Docker MCP Servers"""
    
    def __init__(self, name: str, server_params: StdioServerParameters):
        self.name = name
        self.server_params = server_params
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.tools_map = {}  # Cache tool definitions

    async def connect(self):
        """Establishes stdio connection to the Docker container"""
        if self.session:
            return

        logger.info(f"Connecting to MCP Server [{self.name}]: {self.server_params.command} {' '.join(self.server_params.args)}...")
        
        try:
            # Start the stdio transport
            transport = await self.exit_stack.enter_async_context(
                stdio_client(self.server_params)
            )
            self.read, self.write = transport
            
            # Start the MCP session
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(self.read, self.write)
            )
            await self.session.initialize()
            
            # Fetch available tools and cache them
            result = await self.session.list_tools()
            self.tools_map = {tool.name: tool for tool in result.tools}
            logger.info(f"Connected to [{self.name}]. Loaded {len(self.tools_map)} tools.")
        except Exception as exc:
            logger.error(f"Failed to connect to MCP Server [{self.name}]: {exc}")
            raise

    async def get_openai_tools(self) -> List[Dict]:
        """Convert MCP tool definitions to OpenRouter/OpenAI format"""
        if not self.session:
            await self.connect()
            
        openai_tools = []
        for tool in self.tools_map.values():
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema  # MCP inputSchema maps 1:1 to OpenAI parameters
                }
            })
        return openai_tools

    async def call_tool(self, name: str, arguments: Dict) -> str:
        """Execute the tool on the Docker container"""
        if not self.session:
            raise RuntimeError(f"MCP Session [{self.name}] not connected")
            
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
        """Close connection and cleanup resources"""
        logger.info(f"Cleaning up MCP Server [{self.name}]")
        try:
            # Shield the cleanup to prevent it from being cancelled while running
            with anyio.CancelScope(shield=True):
                await self.exit_stack.aclose()
        except Exception as exc:
            # We catch everything during cleanup to ensure we don't crash during shutdown
            logger.debug(f"Interruption or error during cleanup of [{self.name}]: {exc}")


class WebSearchAgent:
    """Specialized agent using OpenRouter Responses API for web search with task-safe caching"""
    
    def __init__(self, api_key: str, model: str = cfg.config.WEB_SEARCH_MODEL):
        self.api_key = api_key
        self.model = model
        self.base_url = OPENROUTER_RESPONSES_ENDPOINT
        self.search_cache = {}  # Semantic cache to avoid redundant web hits
        self.cache_lock = asyncio.Lock()
        
    async def search(self, query: str, max_results: int = 3) -> str:
        """
        Execute web search via OpenRouter Responses API.
        Implements single-flight pattern via lock to prevent redundant concurrent searches.
        """
        # Normalize query for caching
        cache_key = query.strip().lower()
        
        async with self.cache_lock:
            if cache_key in self.search_cache:
                logger.info(f"WebSearchAgent: Serving cached result for query: '{query}'")
                return self.search_cache[cache_key]
                
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
                "plugins": [{"id": "web", "max_results": max_results}]
            }
            
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    response = await client.post(
                        self.base_url,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload
                    )
                    response.raise_for_status()
                    result = response.json()
                    
                    # Extract content from Responses API output
                    # The Responses API returns multiple items in output array:
                    # - First item is typically "reasoning" with encrypted content
                    # - Subsequent items are "message" types with actual content
                    output_content = ""
                    if "output" in result and result["output"]:
                        for output_item in result["output"]:
                            # Skip reasoning/encrypted items, look for message types
                            if output_item.get("type") == "message":
                                content_list = output_item.get("content", [])
                                for part in content_list:
                                    part_type = part.get("type")
                                    if part_type in ["text", "output_text"]:
                                        output_content += part.get("text", "")
                            
                    final_result = output_content.strip() or "No information found on the web for this query."
                    self.search_cache[cache_key] = final_result
                    return final_result
                    
            except Exception as exc:
                logger.error(f"WebSearchAgent: API failure: {exc}")
                return f"Error performing web search: {str(exc)}"


class AgentBridge:
    """
    Wrapper to expose an internal agent as a callable tool for other agents.
    Mimics MCPBridge interface for seamless integration.
    """
    
    def __init__(self, name: str, web_agent: WebSearchAgent):
        self.name = name
        self.web_agent = web_agent
        self.tools_map = cfg.WEB_SEARCH_TOOL_DEFINITION

    async def get_openai_tools(self) -> List[Dict]:
        """Convert internal tool definitions to OpenAI tool format"""
        tools = []
        for tool in self.tools_map.values():
            tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["inputSchema"]
                }
            })
        return tools

    async def call_tool(self, name: str, arguments: Dict) -> str:
        """Route tool call to the internal WebSearchAgent"""
        if name == "web_search":
            query = arguments.get("query")
            max_results = arguments.get("max_results", 3)
            if not query:
                return "Error: Missing search query."
            return await self.web_agent.search(query, max_results)
        return f"Error: Tool {name} not supported by this bridge."


class Agent:
    """Investment research agent with hybrid profile and MCP tool calling capability"""
    
    def __init__(
        self, 
        profile: AgentProfile, 
        api_key: str, 
        model: str = cfg.config.PRIMARY_MODEL,
        mcp_bridge: Optional[MCPBridge] = None,
        agent_bridge: Optional[AgentBridge] = None
    ):
        self.profile = profile
        self.api_key = api_key
        self.model = model
        self.mcp_bridge = mcp_bridge
        self.agent_bridge = agent_bridge
        self.base_url = OPENROUTER_CHAT_ENDPOINT
    
    def _build_system_prompt(self) -> str:
        """Build system prompt using full markdown specification (hybrid approach)"""
        return self.profile.full_spec
    
    async def analyze(self, query: str) -> str:
        """
        Execute analysis task with tool-calling loop, retry logic and error handling.
        Adheres to agentic focus with deterministic tool execution and circuit breakers.
        """
        messages = [
            {"role": "system", "content": self.profile.full_spec},
            {"role": "user", "content": query}
        ]
        
        # Tools can come from multiple sources (MCP servers or other Agents)
        available_tools = []
        if self.mcp_bridge:
            mcp_tools = await self.mcp_bridge.get_openai_tools()
            available_tools.extend(mcp_tools)
        if self.agent_bridge:
            agent_tools = await self.agent_bridge.get_openai_tools()
            available_tools.extend(agent_tools)
        
        tool_iteration_count = 0
        
        for attempt_index in range(cfg.config.MAX_RETRIES):
            try: 
                while True:  # Core Agentic Loop
                    payload = {
                        "model": self.model,
                        "messages": messages
                    }
                    if available_tools:
                        payload["tools"] = available_tools
                        payload["tool_choice"] = "auto"

                    async with httpx.AsyncClient(timeout=None) as client:
                        logger.info(f"{self.profile.name}: Requesting LLM (Attempt {attempt_index + 1})")
                        logger.debug(f"{self.profile.name}: [DEBUG] Using URL: {self.base_url}")
                        
                        response = await client.post(
                            self.base_url,
                            headers={
                                "Authorization": f"Bearer {self.api_key}",
                                "Content-Type": "application/json"
                            },
                            json=payload
                        )
                        response.raise_for_status()
                        llm_result = response.json()
                        
                        assistant_message = llm_result["choices"][0]["message"]
                        
                        # CASE A: Final Text Response received
                        if not assistant_message.get("tool_calls"):
                            final_analysis_text = assistant_message["content"]
                            logger.info(f"{self.profile.name}: Analysis complete ({len(final_analysis_text or '')} chars)")
                            return final_analysis_text or "No content returned."

                        # CASE B: Tool Calls Requested by LLM
                        tool_iteration_count += 1
                        messages.append(assistant_message) # Maintain conversation state
                        
                        for requested_tool in assistant_message["tool_calls"]:
                            target_tool_name = requested_tool["function"]["name"]
                            tool_arguments = json.loads(requested_tool["function"]["arguments"])
                            
                            logger.info(f"{self.profile.name}: LLM suggested tool -> {target_tool_name}")
                            
                            # Route the tool call to the correct bridge
                            if self.mcp_bridge and target_tool_name in self.mcp_bridge.tools_map:
                                execution_result = await self.mcp_bridge.call_tool(target_tool_name, tool_arguments)
                            elif self.agent_bridge and target_tool_name in self.agent_bridge.tools_map:
                                execution_result = await self.agent_bridge.call_tool(target_tool_name, tool_arguments)
                            else:
                                execution_result = f"Error: Tool {target_tool_name} not found in this agent's bridge context."
                            
                            messages.append({
                                "role": "tool",
                                "tool_call_id": requested_tool["id"],
                                "name": target_tool_name,
                                "content": execution_result
                            })
                        
                        # Re-enter loop to feed tool outputs back to LLM
                        
            except httpx.HTTPStatusError as http_error:
                if http_error.response.status_code == 429:
                    # Respect API's Retry-After or apply exponential backoff
                    retry_after_header = http_error.response.headers.get("Retry-After")
                    
                    try:
                        backoff_seconds = int(retry_after_header) if retry_after_header else min(2 ** attempt_index, cfg.config.RATE_LIMIT_BACKOFF_CAP)
                    except ValueError:
                        backoff_seconds = 60 # Default to 60s if header is a date string
                    
                    logger.warning(f"{self.profile.name}: Rate limited (429). Backing off for {backoff_seconds}s. (Attempt {attempt_index + 1})")
                    await anyio.sleep(backoff_seconds)
                else:
                    logger.error(f"{self.profile.name}: API Error {http_error.response.status_code} (Attempt {attempt_index + 1})")
                    if attempt_index == MAX_RETRIES - 1: raise
                    await anyio.sleep(2 ** attempt_index)
                
            except Exception as unexpected_error:
                logger.error(f"{self.profile.name}: Unexpected failure (Attempt {attempt_index + 1}): {unexpected_error}")
                if attempt_index == MAX_RETRIES - 1: raise
                await anyio.sleep(2 ** attempt_index)
        
        raise RuntimeError(f"{self.profile.name}: Could not reach analysis goals within {cfg.config.MAX_RETRIES} attempts.")

    async def answer_question(self, question: str, original_analysis: str) -> str:
        """
        Answer follow-up clarification questions from synthesis agent
        """
        prompt = cfg.FOLLOW_UP_PROMPT_TEMPLATE.format(
            original_analysis=original_analysis,
            question=question,
            specialization=self.profile.specialization
        )
        return await self.analyze(prompt)


class AgentDefinitionParser:
    """Parse agent definition files with hybrid approach"""
    
    @staticmethod
    def parse_markdown(content: str) -> AgentProfile:
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


class MultiAgentOrchestrator:
    """Orchestrate multi-agent investment research workflow with MCP bridges"""
    
    # --- Workflow Constants ---
    PHASE_THROTTLE_SECONDS = cfg.config.PHASE_THROTTLE_SECONDS
    
    def __init__(
        self, 
        agents_dir: str = None,
        model_name: str = None,
        mode: str = "all",
        output_directory: str = cfg.config.OUTPUT_DIR
    ):
        self.mode = mode.lower()
        if self.mode not in ["fundamental", "momentum", "all"]:
            raise ValueError("Invalid mode. Must be 'fundamental', 'momentum', or 'all'")

        # Strict environment validation
        cfg.config.validate()
        self.api_key = cfg.config.OPENROUTER_API_KEY
        
        # Determine absolute path for agent definitions
        if agents_dir is None:
            agents_dir = str(Path(__file__).parent / "agent-definition-files")
        self.agents_dir = Path(agents_dir)
        
        # Model configuration
        self.model = model_name or cfg.config.PRIMARY_MODEL
            
        self.output_dir = Path(output_directory)
        self.output_dir.mkdir(exist_ok=True)
        
        # GraphRAG path validation (required for Docker sibling volume mounts)
        registry_path = cfg.config.GRAPHRAG_REGISTRY_DIR
        project_home_path = cfg.config.GRAPHRAG_PROJECT_PATH
        
        if not registry_path or not project_home_path:
            raise ValueError("GRAPHRAG_REGISTRY_DIR or GRAPHRAG_PROJECT_PATH not set in .env")
            
        # Initialize MCP Bridges (Docker-out-of-Docker / DooD architecture)
        self.bridges: Dict[str, MCPBridge] = {
            "finance": MCPBridge("finance-tools", StdioServerParameters(
                command="docker",
                args=["run", "-i", "--rm", cfg.config.FINANCE_TOOLS_IMAGE],
                env=None
            )),
            "graphrag": MCPBridge("graphrag", StdioServerParameters(
                command="docker",
                args=[
                    "run", "-i", "--rm",
                    "-v", f"{project_home_path}:/app",
                    "-v", f"{cfg.config.GRAPHRAG_NODE_MODULES_VOLUME}:/app/node_modules",
                    "-v", f"{registry_path}:/root/.graphrag",
                    "-v", f"{project_home_path}/.DuckDB:/app/.DuckDB",
                    "-v", f"{project_home_path}/output:/app/output",
                    "--add-host=host.docker.internal:host-gateway",
                    
                    "-e", f"OPENROUTER_API_KEY={self.api_key}",
                    "-e", f"GRAPHRAG_DATABASE={cfg.config.GRAPHRAG_DATABASE}",
                    "-e", "NODE_NO_WARNINGS=1",
                    
                    cfg.config.GRAPHRAG_IMAGE,
                    "npx", "tsx", "mcp_server.ts"
                ],
                env=None
            ))
        }
        
        # Initialize specialized Web Search Agent (delegated librarian)
        web_search_model = cfg.config.WEB_SEARCH_MODEL
        self.web_search_agent = WebSearchAgent(self.api_key, model=web_search_model)
        
        # Wrap the web search agent in a bridge to make it callable as a tool
        self.web_search_bridge = AgentBridge("web-search", self.web_search_agent)
        
        # Bootstrap qualitative and quantitative agents
        # Qualitative agent gets GraphRAG + Web Search
        self.qualitative_agent = self._load_agent_module(
            "qualitative_agent.md", 
            mcp_bridge=self.bridges["graphrag"],
            agent_bridge=self.web_search_bridge
        )
        
        # Quantitative agent stays purely financial (no web search to prevent noise)
        self.quantitative_agent = self._load_agent_module(
            "quantitative_agent.md", 
            mcp_bridge=self.bridges["finance"]
        )
        
        # Synthesis agent gets Web Search for final gap filling
        self.synthesis_agent = self._load_agent_module(
            "synthesis_agent.md",
            agent_bridge=self.web_search_bridge
        )
        
        # Momentum agent (optional depending on mode, but loaded for simplicity)
        self.momentum_agent = self._load_agent_module(
            "momentum_agent.md",
            agent_bridge=self.web_search_bridge
        )
        
        logger.info(f"Orchestrator online. Mode: {self.mode} | Model: {self.model}")
    
    def _load_agent_module(
        self, 
        filename: str, 
        mcp_bridge: Optional[MCPBridge] = None,
        agent_bridge: Optional[AgentBridge] = None
    ) -> Agent:
        """Instantiate an agent from a markdown definition file"""
        full_path = self.agents_dir / filename
        with open(full_path, 'r', encoding='utf-8') as agent_file:
            raw_content = agent_file.read()
        agent_profile = AgentDefinitionParser.parse_markdown(raw_content)
        return Agent(agent_profile, self.api_key, self.model, mcp_bridge, agent_bridge)
    
    async def cleanup(self):
        """Standard teardown for all active MCP bridges"""
        for active_bridge in self.bridges.values():
            await active_bridge.cleanup()

    async def research(self, investment_query: str) -> Dict:
        """
        Executes the full multi-agent workflow:
        Phase 1: Parallel Specialized Analysis
        Phase 2: Initial Synthesis
        Phase 3: Recursive Clarification
        Phase 4: Final Unified Thesis
        """
        logger.info(f"\n[RESEARCH QUERY] {investment_query}\n")
        
        try:
            # Pre-connect bridges to ensure task consistency (cancel scope shielding)
            for bridge_name, target_bridge in self.bridges.items():
                try:
                    await target_bridge.connect()
                except Exception as connection_err:
                    logger.warning(f"Bridge connection standby failure [{bridge_name}]: {connection_err}")

            # Phase 1: Parallel specialized analysis
            logger.info("PHASE 1: Execution started (Qual/Quant agents)...")
            
            analysis_snapshots = {}
            async with anyio.create_task_group() as task_group:
                async def _run_qualitative():
                    analysis_snapshots['qual'] = await self._invoke_agent_safe(self.qualitative_agent, investment_query)
                async def _run_quantitative():
                    analysis_snapshots['quant'] = await self._invoke_agent_safe(self.quantitative_agent, investment_query)
                
                task_group.start_soon(_run_qualitative)
                task_group.start_soon(_run_quantitative)

            qual_results = analysis_snapshots['qual']
            quant_results = analysis_snapshots['quant']
            
            if qual_results.error or quant_results.error:
                return {
                    "error": "Specialized analysis phase failed",
                    "qual_error": qual_results.error,
                    "quant_error": quant_results.error
                }

            await anyio.sleep(cfg.config.PHASE_THROTTLE_SECONDS)

            await anyio.sleep(cfg.config.PHASE_THROTTLE_SECONDS)

            # Phase 2: Synthesis / Momentum Analysis
            logger.info(f"PHASE 2: Generating analysis (Mode: {self.mode})...")
            
            synthesis_input = cfg.SYNTHESIS_INPUT_TEMPLATE.format(
                qual_analysis=qual_results.analysis,
                quant_analysis=quant_results.analysis
            )

            results_map = {
                "qualitative": {"analysis": qual_results.analysis, "clarification": ""},
                "quantitative": {"analysis": quant_results.analysis, "clarification": ""},
                "synthesis": {},
                "momentum": {}
            }

            # --- Fundamental Synthesis Path ---
            if self.mode in ["fundamental", "all"]:
                # Initial synthesis
                initial_synth = await self.synthesis_agent.analyze(synthesis_input)
                await anyio.sleep(cfg.config.PHASE_THROTTLE_SECONDS)

                # Recursive Clarification
                logger.info("PHASE 3 (Fundamental): Seeking cross-agent clarifications...")
                qual_clarification = await self.qualitative_agent.answer_question(
                    cfg.QUAL_RECURSIVE_QUESTION, qual_results.analysis
                )
                quant_clarification = await self.quantitative_agent.answer_question(
                    cfg.QUANT_RECURSIVE_QUESTION, quant_results.analysis
                )
                
                results_map["qualitative"]["clarification"] = qual_clarification
                results_map["quantitative"]["clarification"] = quant_clarification
                
                await anyio.sleep(cfg.config.PHASE_THROTTLE_SECONDS)

                # Final Consolidation
                logger.info("PHASE 4 (Fundamental): Consolidating confirmation...")
                final_prompt = cfg.FINAL_CONSOLIDATION_TEMPLATE.format(
                    initial_synthesis=initial_synth,
                    qual_clarification=qual_clarification,
                    quant_clarification=quant_clarification
                )
                final_recommendation = await self.synthesis_agent.analyze(final_prompt)
                results_map["synthesis"]["final_recommendation"] = final_recommendation

            # --- Momentum Analysis Path ---
            if self.mode in ["momentum", "all"]:
                logger.info("PHASE 2b (Momentum): Generating swing trade analysis...")
                
                # Momentum agent consumes raw Qual/Quant + any clarifications if available
                # If we skipped fundamental path, clarifications are empty, which is fine
                momentum_input = cfg.MOMENTUM_CONSOLIDATION_TEMPLATE.format(
                    qual_analysis=qual_results.analysis,
                    quant_analysis=quant_results.analysis,
                    qual_clarification=results_map["qualitative"]["clarification"] or "N/A (Fundamental Mode Skipped)",
                    quant_clarification=results_map["quantitative"]["clarification"] or "N/A (Fundamental Mode Skipped)"
                )
                
                momentum_analysis = await self.momentum_agent.analyze(momentum_input)
                results_map["momentum"]["analysis"] = momentum_analysis

            # Construct Result Object
            research_result = {
                "query": investment_query,
                "timestamp": datetime.now().isoformat(),
                "mode": self.mode,
                "agents": results_map
            }
            
            # Save final report to file
            self.save_results(research_result)
            return research_result

        except Exception as exc:
            logger.error(f"Research error: {exc}", exc_info=True)
            return {"error": str(exc)}
        finally:
            await self.cleanup()

    async def _invoke_agent_safe(self, agent: Agent, task: str) -> ResearchResult:
        """Shielded agent execution to prevent individual failure from crashing the group"""
        try:
            analysis_output = await agent.analyze(task)
            return ResearchResult(agent.profile.name, analysis_output, datetime.now())
        except Exception as invocation_error:
            logger.error(f"Agent invocation failed [{agent.profile.name}]: {invocation_error}")
            return ResearchResult(agent.profile.name, "", datetime.now(), str(invocation_error))

    def save_results(self, result: Dict):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.output_dir / f"research_{result['mode']}_{timestamp}.md"
        
        # Base report with Qual/Quant data (always present)
        report_md = cfg.MARKDOWN_REPORT_TEMPLATE.format(
            query=result['query'],
            qual_analysis=result['agents']['qualitative']['analysis'],
            qual_clarification=result['agents']['qualitative']['clarification'],
            quant_analysis=result['agents']['quantitative']['analysis'],
            quant_clarification=result['agents']['quantitative']['clarification'],
            final_recommendation=result['agents'].get('synthesis', {}).get('final_recommendation', 'N/A (Momentum Mode Only)')
        )
        
        # Append Momentum Section if active
        if result['mode'] in ['momentum', 'all']:
            momentum_section = cfg.MOMENTUM_REPORT_SECTION.format(
                momentum_analysis=result['agents']['momentum']['analysis']
            )
            report_md += momentum_section
        
        with open(path, 'w', encoding='utf-8') as report_file:
            report_file.write(report_md)
        logger.info(f"Report saved to {path}")



async def main():
    try:
        cfg.config.validate()
    except ValueError as e:
        print(e)
        return
        
    query = input(f"Enter investment query [{cfg.config.DEFAULT_INVESTMENT_QUERY}]: ").strip() or cfg.config.DEFAULT_INVESTMENT_QUERY
    
    print("\nSelect Analysis Mode:")
    print("1. Fundamental (Long-term value synthesis)")
    print("2. Momentum (Swing trade swing setup)")
    print("3. All (Comprehensive report)")
    mode_selection = input("Choice [3]: ").strip()
    
    mode_map = {"1": "fundamental", "2": "momentum", "3": "all"}
    selected_mode = mode_map.get(mode_selection, "all")
    
    orchestrator = MultiAgentOrchestrator(mode=selected_mode)
    result = await orchestrator.research(query)
    
    if "error" not in result:
        print("\n=== ANALYSIS COMPLETE ===")
        print(f"Report generated in: {result['mode']} mode")
    else:
        print(f"\nError: {result['error']}")

if __name__ == "__main__":
    anyio.run(main)

