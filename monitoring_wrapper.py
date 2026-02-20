# ABOUTME: Monitoring state and aspect-oriented logging for the multi-agent system.
# ABOUTME: Intercepts core business logic to provide real-time visibility into agent activity.
# ABOUTME: totalTokens is DERIVED from per-agent buckets — single source of truth.

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
import functools
from contextvars import ContextVar
from dataclasses import dataclass, asdict

try:
    from multi_agent_investment import ResearchOrchestrator
    from agent_engine import Agent, McpToolProvider, InternalAgentAdapter
    import multi_agent_investment
    HAS_ORCHESTRATOR = True
except ImportError:
    HAS_ORCHESTRATOR = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    cost: float = 0.0

    def add(self, other: 'TokenUsage'):
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens
        self.cached_tokens += other.cached_tokens
        self.reasoning_tokens += other.reasoning_tokens
        self.cost += other.cost

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)



class MonitoringState:
    """In-memory state for current research workflow"""
    def __init__(self):
        self.workflowId: Optional[str] = None
        self.query: Optional[str] = None
        self.mode: Optional[str] = None
        self.currentPhase: str = "Idle"
        self.agents: Dict[str, Dict[str, Any]] = {}
        self.toolCalls: List[Dict[str, Any]] = []
        self.startTime: Optional[str] = None
        self.endTime: Optional[str] = None
        self.totalCharsSaved: int = 0

    @property
    def usage(self) -> TokenUsage:
        """Aggregate usage from all agents."""
        total = TokenUsage()
        for agent in self.agents.values():
            if "usage" in agent:
                total.add(agent["usage"])
        return total

    @property
    def totalTokens(self) -> int:
        """Derived from agent-level tracking — single source of truth."""
        return self.usage.total_tokens

    def reset(self, workflowId: str, query: str, mode: str):
        self.workflowId = workflowId
        self.query = query
        self.mode = mode
        self.startTime = datetime.now().isoformat()
        self.endTime = None
        self.toolCalls = []
        self.totalCharsSaved = 0
        # Reset per-agent counters (preserve agent list for UI)
        for agent in self.agents.values():
            agent["usage"] = TokenUsage()
            agent["toolCallsCount"] = 0
            agent["status"] = "idle"
            agent["progress"] = 0
            agent["currentTask"] = None

        return {
            "workflowId": self.workflowId,
            "query": self.query,
            "mode": self.mode,
            "currentPhase": self.currentPhase,
            "agents": list(self.agents.values()),
            "toolCalls": self.toolCalls[-50:],
            "usage": self.usage.to_dict(),
            "totalTokens": self.totalTokens,
            "totalCharsSaved": self.totalCharsSaved,
            "startTime": self.startTime,
            "endTime": self.endTime
        }
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to a dictionary for API delivery"""
        # Convert agent usage objects to dicts for JSON serialization
        agents_serializable = []
        for agent in self.agents.values():
            a_copy = agent.copy()
            if "usage" in a_copy and isinstance(a_copy["usage"], TokenUsage):
                a_copy["usage"] = a_copy["usage"].to_dict()
            agents_serializable.append(a_copy)

        return {
            "workflowId": self.workflowId,
            "query": self.query,
            "mode": self.mode,
            "currentPhase": self.currentPhase,
            "agents": agents_serializable,
            "toolCalls": self.toolCalls[-50:],
            "usage": self.usage.to_dict(),
            "totalTokens": self.totalTokens,
            "totalCharsSaved": self.totalCharsSaved,
            "startTime": self.startTime,
            "endTime": self.endTime
        }

    def getOptimizationSummary(self) -> Dict[str, Any]:
        """Calculate and return intelligence efficiency metrics.
        actual_tokens is DERIVED from per-agent tracking (post-pruning real cost).
        estimated_pre_pruning_tokens = actual + estimated savings.
        """
        actualTokens = self.totalTokens
        estimatedTokensSaved = self.totalCharsSaved // 4
        estimatedPrePruningTokens = actualTokens + estimatedTokensSaved

        return {
            "actual_tokens": actualTokens,
            "usage": self.usage.to_dict(),
            "total_chars_saved": self.totalCharsSaved,
            "estimated_tokens_saved": estimatedTokensSaved,
            "estimated_pre_pruning_tokens": estimatedPrePruningTokens,
        }

# Global singleton for monitoring state
state = MonitoringState()
currentAgent: ContextVar[Optional[str]] = ContextVar("currentAgent", default=None)

def _parseAgentNames(agentsDir: Path) -> Dict[str, str]:
    """Parse agent names from markdown headers in the definitions directory"""
    names = {}
    if not agentsDir.exists():
        return names
        
    for agentFile in agentsDir.glob("*.md"):
        try:
            with open(agentFile, 'r', encoding='utf-8') as f:
                firstLine = f.readline().strip()
                if firstLine.startswith("# "):
                    names[agentFile.name] = firstLine[2:].strip()
        except Exception as e:
            logger.error(f"Error parsing agent name from {agentFile}: {e}")
    return names

def initialize_monitoring(agentsDir: Path):
    """Pre-populate agent list from definition files"""
    agentNames = _parseAgentNames(agentsDir)
    for filename, displayName in agentNames.items():
        agentId = filename.replace("_agent.md", "")
        state.agents[displayName] = {
            "id": agentId,
            "name": displayName,
            "role": _mapRole(agentId),
            "status": "idle",
            "progress": 0,
            "progress": 0,
            "usage": TokenUsage(),
            "toolCallsCount": 0,
            "currentTask": None
        }

def _mapRole(agentId: str) -> str:
    roles = {
        "qualitative": "Qualitative Intelligence",
        "quantitative": "Quantitative Analysis",
        "synthesis": "Synthesis",
        "momentum": "Momentum Analysis"
    }
    return roles.get(agentId, "Specialist")

def patch_multi_agent():
    """Apply non-invasive patches to the Orchestrator and Agent classes"""
    if not HAS_ORCHESTRATOR:
        logger.error("Could not find multi_agent_investment to patch")
        return

    try:
        
        # 0. Patch logger to track phase transitions
        originalInfo = multi_agent_investment.logger.info
        
        def _wrappedInfo(msg, *args, **kwargs):
            if isinstance(msg, str):
                if "PHASE 1" in msg:
                    state.currentPhase = "Phase 1: Parallel Analysis"
                elif "PHASE 2" in msg:
                    state.currentPhase = "Phase 2: Synthesis"
                elif "PHASE 3" in msg:
                    state.currentPhase = "Phase 3: Clarification"
                elif "PHASE 4" in msg:
                    state.currentPhase = "Phase 4: Thesis"
            return originalInfo(msg, *args, **kwargs)
            
        multi_agent_investment.logger.info = _wrappedInfo

        # 1. Patch ResearchOrchestrator.executeResearchSession
        originalResearch = ResearchOrchestrator.executeResearchSession
        
        @functools.wraps(originalResearch)
        async def _wrappedResearch(self, investmentQuery: str, **kwargs):
            workflowId = f"wf_{datetime.now().strftime('%H%M%S')}"
            state.reset(workflowId, investmentQuery, self.mode)
            logger.info(f"Monitoring started for research session: {workflowId}")
            
            # Ensure agent monitoring is initialized with the orchestrator's agent dir
            initialize_monitoring(self.agentsDir)
            
            try:
                result = await originalResearch(self, investmentQuery, **kwargs)
                state.currentPhase = "Complete"
                state.endTime = datetime.now().isoformat()
                return result
            except Exception as e:
                state.currentPhase = "Error"
                logger.error(f"Error in research session: {e}")
                raise

        ResearchOrchestrator.executeResearchSession = _wrappedResearch
        
        # 2. Patch Agent.performResearchTask to capture usage and activity
        originalAnalyze = Agent.performResearchTask
        
        @functools.wraps(originalAnalyze)
        async def _wrappedAnalyze(self, query: str):
            name = self.profile.name
            token = currentAgent.set(name)
            
            if name in state.agents:
                state.agents[name]["status"] = "active"
                state.agents[name].setdefault("currentTask", "")
                state.agents[name]["currentTask"] = query
                state.agents[name]["progress"] = 25
            
            try:
                result = await originalAnalyze(self, query)

                # Read usage directly from the structured ChatResponse —
                # provider-agnostic and guaranteed consistent by _normalizeUsage in llm_client.
                if self.lastResponse and self.lastResponse.usage:
                    usage = self.lastResponse.usage
                    current_usage = TokenUsage(
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        total_tokens=usage.get("total_tokens", 0),
                    )
                    if name in state.agents:
                        state.agents[name]["usage"].add(current_usage)
                    else:
                        # Route unattributed tokens to orchestrator bucket
                        if "_orchestrator" not in state.agents:
                            state.agents["_orchestrator"] = {
                                "id": "orchestrator",
                                "name": "Orchestrator",
                                "role": "Synthesis",
                                "status": "active",
                                "progress": 0,
                                "usage": TokenUsage(),
                                "toolCallsCount": 0,
                                "currentTask": "System orchestration"
                            }
                        state.agents["_orchestrator"]["usage"].add(current_usage)
                        logger.warning(f"Unattributed tokens ({current_usage.total_tokens}) assigned to Orchestrator (agent: {name})")

                # Capture last thought/content for activity feed
                if self.lastResponse and self.lastResponse.content:
                    content = self.lastResponse.content
                    state.toolCalls.append({
                        "id": f"thought_{datetime.now().strftime('%H%M%S%f')}",
                        "toolName": "THOUGHT",
                        "agentName": name,
                        "arguments": {"thought": content[:500] + ("..." if len(content) > 500 else "")},
                        "timestamp": datetime.now().isoformat(),
                        "executionTimeMs": 0
                    })

                if name in state.agents:
                    state.agents[name]["status"] = "completed"
                    state.agents[name]["progress"] = 100
                    state.agents[name]["currentTask"] = "Analysis finished."
                return result
            except Exception as e:
                if name in state.agents:
                    state.agents[name]["status"] = "error"
                    state.agents[name]["currentTask"] = f"Error: {str(e)}"
                raise
            finally:
                currentAgent.reset(token)

        Agent.performResearchTask = _wrappedAnalyze
        
        # 3. Patch McpToolProvider.executeMcpTool to track tool activity
        originalCall = McpToolProvider.executeMcpTool
        
        @functools.wraps(originalCall)
        async def _wrappedCallTool(self, name: str, arguments: Dict):
            startTime = datetime.now()
            agentName = currentAgent.get()
            
            try:
                result = await originalCall(self, name, arguments)
                duration = (datetime.now() - startTime).total_seconds() * 1000
                
                state.toolCalls.append({
                    "id": f"tc_{datetime.now().strftime('%H%M%S%f')}",
                    "toolName": name,
                    "agentName": agentName,
                    "arguments": arguments,
                    "timestamp": datetime.now().isoformat(),
                    "executionTimeMs": int(duration)
                })
                
                if agentName and agentName in state.agents:
                    state.agents[agentName]["toolCallsCount"] += 1
                
                return result
            except Exception as e:
                raise

        McpToolProvider.executeMcpTool = _wrappedCallTool
        
        # 3b. Patch InternalAgentAdapter.executeMcpTool (same tracking for web search tools)
        originalAdapterCall = InternalAgentAdapter.executeMcpTool
        
        @functools.wraps(originalAdapterCall)
        async def _wrappedAdapterCallTool(self, name: str, arguments: Dict):
            startTime = datetime.now()
            agentName = currentAgent.get()
            
            try:
                result = await originalAdapterCall(self, name, arguments)
                duration = (datetime.now() - startTime).total_seconds() * 1000
                
                state.toolCalls.append({
                    "id": f"tc_{datetime.now().strftime('%H%M%S%f')}",
                    "toolName": name,
                    "agentName": agentName,
                    "arguments": arguments,
                    "timestamp": datetime.now().isoformat(),
                    "executionTimeMs": int(duration)
                })
                
                if agentName and agentName in state.agents:
                    state.agents[agentName]["toolCallsCount"] += 1
                
                return result
            except Exception as e:
                raise
        
        InternalAgentAdapter.executeMcpTool = _wrappedAdapterCallTool
        
        # 4. Patch output_pruner.pruneAgentOutput to track savings
        try:
            import output_pruner
            originalPrune = output_pruner.pruneAgentOutput
            
            @functools.wraps(originalPrune)
            def _wrappedPrune(rawOutput, maxChars=0, agentType="general"):
                original_len = len(rawOutput) if rawOutput else 0
                result = originalPrune(rawOutput, maxChars, agentType)
                pruned_len = len(result)
                
                # Update Monitoring State
                chars_saved = (original_len - pruned_len)
                state.totalCharsSaved += chars_saved
                
                # Active Monitoring Log (Centralized here, not in the functional pruner)
                if original_len > 0 and chars_saved > 0:
                    reduction_pct = (chars_saved / original_len) * 100
                    logger.info(f"Pruning Impact [{agentType}]: {original_len} -> {pruned_len} chars ({reduction_pct:.1f}% reduction)")
                
                return result
            
            output_pruner.pruneAgentOutput = _wrappedPrune
            # ALSO patch the local reference in multi_agent_investment
            multi_agent_investment.pruneAgentOutput = _wrappedPrune
            logger.info("Successfully patched Output Pruner in all modules.")
        except Exception as pruneError:
            logger.warning(f"Could not patch Output Pruner: {pruneError}")
        
        logger.info("Successfully patched Multi-Agent System for monitoring.")
        
    except ImportError as e:
        logger.error(f"Could not find dependencies to patch: {e}")
    except Exception as e:
        logger.error(f"Failed to patch multi-agent system: {e}")

if __name__ == "__main__":
    # Test initialization
    agentsPath = Path(__file__).parent / "agent-definition-files"
    initialize_monitoring(agentsPath)
    print(json.dumps(state.to_dict(), indent=2))
