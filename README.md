# Multi-Agent Investment Research System

A sophisticated coordination system for automated investment research. It leverages a multi-agent architecture to synthesize qualitative, quantitative, and momentum-based insights using LLM agents and the Model Context Protocol (MCP).

## Purpose and Scope

The system is designed to provide professional-grade investment analysis by orchestrating specialized agents. It handles data retrieval via external tools, applies domain-specific reasoning, and generates comprehensive research reports.

- **Qualitative Intelligence**: Long-term value synthesis and structural risk assessment.
- **Quantitative Analysis**: Financial metrics validation, stability indicators, and growth projections.
- **Momentum Analysis**: Technical setups and swing trade opportunities.
- **Synthesis Engine**: Recursively validates and consolidates insights into a final thesis.

## Architecture

The system follows a modular, agentic design pattern:

- **Orchestration**: `MultiAgentOrchestrator` (in `multi_agent_investment.py`) manages the 4-phase research workflow (Analysis, Synthesis, Clarification, Thesis).
- **Agent Specification**: Personas are defined as Markdown files in `agent-definition-files/`. These are parsed at runtime to build system prompts dynamically.
- **Tooling (MCP)**: `MCPBridge` enables agents to interact with Docker-based MCP servers (`finance-tools`, `graphrag`) via a standardized JSON-RPC interface.
- **Observability**:
  - `monitoring_wrapper.py`: Non-invasively intercepts core methods using `functools.wraps` to track token usage, tool calls, and phase transitions.
  - `api_server.py`: A FastAPI instance providing a real-time status endpoint (`/api/status`).
- **Configuration**: `internal_configs.py` centralizes tool schemas, report templates, and prompt fragments.

## Setup and Development

### Prerequisites

- **Docker Desktop**: Required to host the MCP tool containers and the research engine.
- **OpenRouter API Key**: Set in `.env` for access to primary LLM models.
- **PowerShell (Windows)**: Required for the convenient alias script.

### Installation

Install the `invest-research` alias:

```powershell
.\setup-alias.ps1
# Then restart your terminal or refresh the profile:
. $PROFILE
```

### Running Research

```powershell
# Using the alias (recommended)
invest-research

# Using Docker Compose directly
docker compose run --rm investment-research
```

### Local Development

To set up a local Python environment for linting:

```bash
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

## Testing Procedures

The project adheres to **Test-Driven Development (TDD)**:

1. **Unit Tests**: Implement logic tests for orchestrator phases.
2. **Integration Tests**: Verify bridge connectivity with Docker-based MCP servers.
3. **Verification**: Run tests before committing new agent logic or bridge modifications.
   _Note: Ensure the Docker daemon is running before executing integration tests._

## Key Conventions and Patterns

- **Sustainable Engineering**: Prioritize maintainability over "vibe coding". Every file must start with `ABOUTME` headers.
- **Agentic Interface Design**: Tool functions must have comprehensive docstrings, typed parameters, and deterministic JSON outputs.
- **Intent-based Naming**: Use names like `calculateRiskScore` instead of generic `get_data`.
- **Bulk & Efficiency**: Prefer batch API calls (e.g., bulk price fetching) over individual requests to minimize token latency.
- **Data Standards**: All data points must be normalized (e.g., ISO timestamps).

## Project Structure

- `multi_agent_investment.py`: Core orchestrator and agent logic.
- `agent-definition-files/`: Personas for specialized agents.
- `internal_configs.py`: Tool definitions and prompt templates.
- `monitoring_wrapper.py`: Middleware for observability.
- `output/`: Directory for generated research reports.

---

_This README serves as the primary context contract for AI assistants entering the codebase. Design intent is prioritized over implementation details._
