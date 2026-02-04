from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import os
import asyncio
from monitoring_wrapper import state, patch_multi_agent, initialize_monitoring

# ABOUTME: FastAPI server providing polling endpoints for the agent monitoring system.
# ABOUTME: Bridges the Python multi-agent system with the React frontend.

app = FastAPI(title="Agent Monitoring API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict to frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize and patch on startup
@app.on_event("startup")
async def startup_event():
    # Patch the multi-agent system
    patch_multi_agent()
    
    # Initialize agent list
    agents_dir = Path(__file__).parent / "agent-definition-files"
    initialize_monitoring(agents_dir)

@app.get("/api/status")
async def get_status():
    """Polling endpoint for the frontend to get current workflow state"""
    return state.to_dict()

@app.get("/api/health")
async def health():
    return {"status": "ok"}

@app.post("/api/research")
async def start_research(query: str, mode: str = "all"):
    """
    Trigger research via API (for testing monitoring)
    In a real scenario, this would import the orchestrator and run it.
    """
    from multi_agent_investment import MultiAgentOrchestrator
    
    orchestrator = MultiAgentOrchestrator(mode=mode)
    
    # Run research in background so API remains responsive
    async def run_research():
        try:
            await orchestrator.research(query)
        except Exception as e:
            print(f"Research failed: {e}")
            
    asyncio.create_task(run_research())
    
    return {"message": "Research started", "workflowId": state.workflow_id}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
