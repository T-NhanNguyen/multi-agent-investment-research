from fastapi import FastAPI, BackgroundTasks
from multi_agent_investment import ResearchOrchestrator
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import os
import asyncio
import logging
import internal_configs as cfg
from monitoring_wrapper import state, patch_multi_agent, initialize_monitoring

logger = logging.getLogger(__name__)

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
    Trigger research via the monitoring API.
    The orchestrator is created and connected inside the background task to ensure
    anyio/MCP context managers run within the same task scope (avoiding task boundary errors).
    """
    # Assign a preliminary workflow ID early so the frontend can track it
    import uuid
    workflowId = str(uuid.uuid4())
    state.workflowId = workflowId
    state.currentPhase = "Initializing"

    async def _runResearch():
        orchestrator = None
        try:
            # Instantiate inside the task so MCP context managers are task-local
            orchestrator = ResearchOrchestrator(mode=mode)
            await orchestrator.executeResearchSession(query)
        except Exception as e:
            logger.error(f"Research task failed (workflowId={workflowId}): {e}", exc_info=True)
            # Surface the error into monitoring state so the UI can reflect it
            state.currentPhase = "Error"
        finally:
            if orchestrator is not None:
                try:
                    await orchestrator.cleanup()
                except Exception as cleanupErr:
                    logger.debug(f"Orchestrator cleanup error: {cleanupErr}")

    # Use get_event_loop().create_task so the coroutine runs in the server's event loop
    asyncio.get_event_loop().create_task(_runResearch())

    return {"message": "Research started", "workflowId": workflowId}

@app.get("/api/papers")
async def _listPapers():
    """Returns a list of all research .md files in the output directory, newest first."""
    outputDir = Path(__file__).parent / "output" / "human-centric_reports"
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
    outputDir = Path(__file__).parent / "output" / "human-centric_reports"
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

@app.get("/api/logs")
async def _listLogs():
    """Returns a list of all raw execution log .md files in the output directory, newest first."""
    outputDir = Path(__file__).parent / "output" / "research_logs"
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

@app.get("/api/logs/{filename}")
async def _getLog(filename: str):
    """Returns the content of a specific execution log."""
    outputDir = Path(__file__).parent / "output" / "research_logs"
    filepath = outputDir / filename
    
    if not filepath.exists() or filepath.suffix != ".md":
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Log not found")
        
    try:
        content = filepath.read_text(encoding="utf-8")
        return {"filename": filename, "content": content}
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
