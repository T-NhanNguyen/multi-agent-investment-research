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
        self.workflow_id: Optional[str] = None
        self.query: Optional[str] = None
        self.mode: Optional[str] = None
        self.current_phase: str = "Idle"
        self.agents: Dict[str, Dict[str, Any]] = {}
        self.tool_calls: List[Dict[str, Any]] = []
        self.start_time: Optional[str] = None
        self.end_time: Optional[str] = None
        self.total_tokens: int = 0

    def reset(self, workflow_id: str, query: str, mode: str):
        self.workflow_id = workflow_id
        self.query = query
        self.mode = mode
        self.current_phase = "Phase 1: Parallel Analysis"
        self.start_time = datetime.now().isoformat()
        self.end_time = None
        self.tool_calls = []
        self.total_tokens = 0
        # Agent status will be updated as they are invoked

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflowId": self.workflow_id,
            "query": self.query,
            "mode": self.mode,
            "currentPhase": self.current_phase,
            "agents": list(self.agents.values()),
            "toolCalls": self.tool_calls[-50:],  # Return only recent calls
            "totalTokens": self.total_tokens,
            "startTime": self.start_time,
            "endTime": self.end_time
        }

# Global singleton for monitoring state
state = MonitoringState()
current_agent: ContextVar[Optional[str]] = ContextVar("current_agent", default=None)

def _parse_agent_names(agents_dir: Path) -> Dict[str, str]:
    """Parse agent names from markdown headers in the definitions directory"""
    names = {}
    if not agents_dir.exists():
        return names
        
    for agent_file in agents_dir.glob("*.md"):
        try:
            with open(agent_file, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                if first_line.startswith("# "):
                    names[agent_file.name] = first_line[2:].strip()
        except Exception as e:
            logger.error(f"Error parsing agent name from {agent_file}: {e}")
    return names

def initialize_monitoring(agents_dir: Path):
    """Pre-populate agent list from definition files"""
    agent_names = _parse_agent_names(agents_dir)
    for filename, display_name in agent_names.items():
        agent_id = filename.replace("_agent.md", "")
        state.agents[display_name] = {
            "id": agent_id,
            "name": display_name,
            "role": _map_role(agent_id),
            "status": "idle",
            "progress": 0,
            "tokensUsed": 0,
            "toolCallsCount": 0,
            "currentTask": None
        }

def _map_role(agent_id: str) -> str:
    roles = {
        "qualitative": "Qualitative Intelligence",
        "quantitative": "Quantitative Analysis",
        "synthesis": "Synthesis",
        "momentum": "Momentum Analysis"
    }
    return roles.get(agent_id, "Specialist")

def patch_multi_agent():
    """Apply non-invasive patches to the Orchestrator and Agent classes"""
    try:
        from multi_agent_investment import MultiAgentOrchestrator, Agent, MCPBridge
        import multi_agent_investment
        import httpx
        import json
        
        # 0. Patch logger to track phase transitions
        original_info = multi_agent_investment.logger.info
        
        def wrapped_info(msg, *args, **kwargs):
            if isinstance(msg, str):
                if "PHASE 1" in msg:
                    state.current_phase = "Phase 1: Parallel Analysis"
                elif "PHASE 2" in msg:
                    state.current_phase = "Phase 2: Synthesis"
                elif "PHASE 3" in msg:
                    state.current_phase = "Phase 3: Clarification"
                elif "PHASE 4" in msg:
                    state.current_phase = "Phase 4: Thesis"
            return original_info(msg, *args, **kwargs)
            
        multi_agent_investment.logger.info = wrapped_info

        # 1. Patch Orchestrator.research
        original_research = MultiAgentOrchestrator.research
        
        @functools.wraps(original_research)
        async def wrapped_research(self, investment_query: str):
            workflow_id = f"wf_{datetime.now().strftime('%H%M%S')}"
            state.reset(workflow_id, investment_query, self.mode)
            logger.info(f"Monitoring started for research: {workflow_id}")
            
            if not state.agents:
                initialize_monitoring(self.agents_dir)
            
            try:
                result = await original_research(self, investment_query)
                state.current_phase = "Complete"
                state.end_time = datetime.now().isoformat()
                return result
            except Exception as e:
                state.current_phase = "Error"
                logger.error(f"Error in research workflow: {e}")
                raise

        MultiAgentOrchestrator.research = wrapped_research
        
        # 2. Patch Agent.analyze to capture usage and thoughts
        original_analyze = Agent.analyze
        
        @functools.wraps(original_analyze)
        async def wrapped_analyze(self, query: str):
            name = self.profile.name
            token = current_agent.set(name)
            
            if name in state.agents:
                state.agents[name]["status"] = "active"
                state.agents[name].setdefault("currentTask", "")
                state.agents[name]["currentTask"] = query
                state.agents[name]["progress"] = 25
            
            # We need to monkeypath the httpx client inside THIS call or the class method
            # But the Agent.analyze creates its own client. 
            # Better: patch httpx.AsyncClient.post globally during this call
            
            original_post = httpx.AsyncClient.post
            
            async def wrapped_post(client_self, url, **kwargs):
                response = await original_post(client_self, url, **kwargs)
                if response.is_success:
                    try:
                        data = response.json()
                        usage = data.get("usage", {})
                        if usage:
                            prompt_tokens = usage.get("prompt_tokens", 0)
                            completion_tokens = usage.get("completion_tokens", 0)
                            total = usage.get("total_tokens", 0)
                            
                            # Update agent and global state
                            if name in state.agents:
                                state.agents[name]["tokensUsed"] += total
                            state.total_tokens += total
                            
                        # Capture thoughts/activity
                        choices = data.get("choices", [])
                        if choices:
                            content = choices[0].get("message", {}).get("content")
                            if content:
                                # Log thought to activity feed
                                state.tool_calls.append({
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

            # Unfortunately patching a local instance's method is hard if it's inside 'async with'.
            # We will patch the class for the duration of this call
            httpx.AsyncClient.post = wrapped_post
            
            try:
                result = await original_analyze(self, query)
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
                httpx.AsyncClient.post = original_post
                current_agent.reset(token)

        Agent.analyze = wrapped_analyze
        
        # 3. Patch MCPBridge.call_tool
        original_call = MCPBridge.call_tool
        
        @functools.wraps(original_call)
        async def wrapped_call_tool(self, name: str, arguments: Dict):
            start_time = datetime.now()
            agent_name = current_agent.get()
            
            try:
                result = await original_call(self, name, arguments)
                duration = (datetime.now() - start_time).total_seconds() * 1000
                
                state.tool_calls.append({
                    "id": f"tc_{datetime.now().strftime('%H%M%S%f')}",
                    "toolName": name,
                    "agentName": agent_name,
                    "arguments": arguments,
                    "timestamp": datetime.now().isoformat(),
                    "executionTimeMs": int(duration)
                })
                
                if agent_name and agent_name in state.agents:
                    state.agents[agent_name]["toolCallsCount"] += 1
                
                return result
            except Exception as e:
                raise

        MCPBridge.call_tool = wrapped_call_tool
        
        logger.info("Successfully patched Multi-Agent System for monitoring.")
        
    except ImportError as e:
        logger.error(f"Could not find dependencies to patch: {e}")
    except Exception as e:
        logger.error(f"Failed to patch multi-agent system: {e}")

if __name__ == "__main__":
    # Test initialization
    agents_path = Path(__file__).parent / "agent-definition-files"
    initialize_monitoring(agents_path)
    print(json.dumps(state.to_dict(), indent=2))
