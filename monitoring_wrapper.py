import json
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import functools
from contextvars import ContextVar

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ABOUTME: Monitoring state and wrapper logic for multi-agent system.
# ABOUTME: Intercepts core business logic to provide real-time updates for PipelineMonitor.

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
        self.totalTokens: int = 0

    def reset(self, workflowId: str, query: str, mode: str):
        self.workflowId = workflowId
        self.query = query
        self.mode = mode
        self.currentPhase = "Phase 1: Parallel Analysis"
        self.startTime = datetime.now().isoformat()
        self.endTime = None
        self.toolCalls = []
        self.totalTokens = 0
        # Agent status will be updated as they are invoked

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflowId": self.workflowId,
            "query": self.query,
            "mode": self.mode,
            "currentPhase": self.currentPhase,
            "agents": list(self.agents.values()),
            "toolCalls": self.toolCalls[-50:],  # Return only recent calls
            "totalTokens": self.totalTokens,
            "startTime": self.startTime,
            "endTime": self.endTime
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
            "tokensUsed": 0,
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
    try:
        from multi_agent_investment import ResearchOrchestrator, Agent, McpToolProvider
        import multi_agent_investment
        import httpx
        import json
        
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
        async def _wrappedResearch(self, investmentQuery: str):
            workflowId = f"wf_{datetime.now().strftime('%H%M%S')}"
            state.reset(workflowId, investmentQuery, self.mode)
            logger.info(f"Monitoring started for research session: {workflowId}")
            
            if not state.agents:
                initialize_monitoring(self.agentsDir)
            
            try:
                result = await originalResearch(self, investmentQuery)
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
            
            originalPost = httpx.AsyncClient.post
            
            async def _wrappedPost(clientSelf, url, **kwargs):
                response = await originalPost(clientSelf, url, **kwargs)
                if response.is_success:
                    try:
                        data = response.json()
                        usage = data.get("usage", {})
                        if usage:
                            total = usage.get("total_tokens", 0)
                            
                            if name in state.agents:
                                state.agents[name]["tokensUsed"] += total
                            state.totalTokens += total
                            
                        # Capture thoughts/activity
                        choices = data.get("choices", [])
                        if choices:
                            content = choices[0].get("message", {}).get("content")
                            if content:
                                state.toolCalls.append({
                                    "id": f"thought_{datetime.now().strftime('%H%M%S%f')}",
                                    "toolName": "THOUGHT",
                                    "agentName": name,
                                    "arguments": {"thought": content[:500] + ("..." if len(content) > 500 else "")},
                                    "timestamp": datetime.now().isoformat(),
                                    "executionTimeMs": 0
                                })
                    except:
                        pass
                return response

            httpx.AsyncClient.post = _wrappedPost
            
            try:
                result = await originalAnalyze(self, query)
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
                httpx.AsyncClient.post = originalPost
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
        
        logger.info("Successfully patched Multi-Agent System for monitoring.")
        
    except ImportError as e:
        logger.error(f"Could not find dependencies to patch: {e}")
    except Exception as e:
        logger.error(f"Failed to patch multi-agent system: {e}")
        
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
