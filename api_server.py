from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import os
import asyncio
import internal_configs as cfg
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
async def _startupEvent():
    # Patch the multi-agent system
    patch_multi_agent()
    
    # Initialize agent list
    agentsDir = Path(__file__).parent / "agent-definition-files"
    initialize_monitoring(agentsDir)

@app.get("/api/status")
async def _getStatus():
    """Polling endpoint for the frontend to get current workflow state"""
    data = state.to_dict()
    # Merge in optimization metrics for the dashboard view
    data["optimization"] = state.getOptimizationSummary()
    return data

@app.get("/api/optimization-summary")
async def _getOptimizationSummary():
    """Detailed intelligence efficiency report for PipelineMonitor"""
    return state.getOptimizationSummary()

@app.get("/api/health")
async def health():
    return {"status": "ok"}

@app.post("/api/research")
async def _startResearch(query: str, mode: str = cfg.config.DEFAULT_RESEARCH_MODE):
    """
    Trigger research via API (for testing monitoring)
    In a real scenario, this would import the orchestrator and run it.
    """
    from multi_agent_investment import ResearchOrchestrator
    
    orchestrator = ResearchOrchestrator(mode=mode)
    
    # Run research in background so API remains responsive
    async def _runResearch():
        try:
            await orchestrator.executeResearchSession(query)
        except Exception as e:
            print(f"Research failed: {e}")
            
    asyncio.create_task(_runResearch())
    
    return {"message": "Research started", "workflowId": state.workflow_id}

@app.get("/api/papers")
async def _listPapers():
    """Returns a list of all research .md files in the output directory, newest first."""
    outputDir = Path(__file__).parent / "output"
    if not outputDir.exists():
        return []
    
    files = sorted(
        outputDir.glob("*.md"),
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )
    return [
        {
            "filename": f.name,
            "size": f.stat().st_size,
            "modified": f.stat().st_mtime
        }
        for f in files
    ]

@app.get("/api/papers/{filename}")
async def _getPaper(filename: str):
    """Returns the content of a specific research paper."""
    outputDir = Path(__file__).parent / "output"
    filepath = outputDir / filename
    
    if not filepath.exists() or filepath.suffix != ".md":
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Paper not found")
        
    try:
        content = filepath.read_text(encoding="utf-8")
        return {"filename": filename, "content": content}
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
