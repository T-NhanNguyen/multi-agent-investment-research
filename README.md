# Multi-Agent Investment Research System

A sophisticated coordination system for automated investment research. It leverages a multi-agent architecture to synthesize qualitative, quantitative, and momentum-based insights using LLM agents and the Model Context Protocol (MCP).

## Recent Progress & Milestones (v1.1)

- **Local LLM Runner Integration**: Added support for local inference via `LocalLlmClient`. The system can now seamlessly switch between OpenRouter and local OpenAI-compatible APIs (Ollama, Docker Model Runner) for cost-efficient development and testing.
- **Modular Phase Architecture**: The orchestration logic has been refactored into distinct, testable phases (`Analysis`, `Synthesis`, `Clarification`, `Consolidation`). This enables deterministic testing of individual reasoning steps.
- **Unified Test Configuration**: Centralized test-time parameters in `tests/test_model_config.py`, providing a single source of truth for mock data, tool images, and LLM endpoints.
- **Enhanced Integration Testing**: Implemented `tests/test_mock_workflow.py` which executes a full research cycle using a local LLM and real MCP tool bridges, verifying the "Bridge to Local Data" pattern end-to-end.

## Architecture

The system follows a modular, agentic design pattern:

- **Orchestration**: `ResearchOrchestrator` (in `multi_agent_investment.py`) manages the 4-phase research workflow. Logic is decoupled from network transport to allow for mock-based unit testing.
- **LLM Transport Layer**: `llm_client.py` provides an abstraction (`ILlmClient`) with implementations for:
  - `OpenRouterClient`: Production-grade API client with exponential backoff.
  - `LocalLlmClient`: Development-grade client for local model runners.
- **Agent Specification**: Personas are defined as Markdown files in `agent-definition-files/`. These are parsed at runtime to build system prompts dynamically.
- **Tooling (MCP)**: `McpToolProvider` enables agents to interact with Docker-based MCP servers (`finance-tools`, `graphrag`) via a standardized JSON-RPC interface.
- **Observability**:
  - `monitoring_wrapper.py`: Non-invasively intercepts core methods to track token usage, tool calls, and phase transitions.
  - `api_server.py`: A FastAPI instance providing a real-time status endpoint (`/api/status`).

## Setup and Development

### Prerequisites

- **Docker Desktop**: Required to host the MCP tool containers and ensure sibling-container networking (via `docker.sock`).
- **OpenRouter API Key**: Set in `.env` for production research.
- **Local LLM Runner**: (Optional) Ollama or Docker Model Runner on `host.docker.internal:12434` for testing.

### Installation

```powershell
.\setup-alias.ps1
# Then refresh the profile:
. $PROFILE
```

### Running Research

```powershell
# Production (OpenRouter)
invest-research

# Integration Testing (Local LLM)
docker-compose run --rm investment-research python tests/test_mock_workflow.py
```

## Testing Procedures

The project adheres to **Test-Driven Development (TDD)**:

1. **Modular Unit Tests**: Using `tests/test_mock_workflow.py` to verify prompt preparation and phase transitions.
2. **Integration Tests**: Using `LocalLlmClient` to verify that agents correctly invoke MCP tools and parse results.
3. **Verification**: Run `docker-compose run --rm investment-research python tests/test_mock_workflow.py` before any major logic commit.

## Key Conventions and Patterns

- **Bridge to Local Data**: Tools like GraphRAG are executed via Docker with volume mounts to the host's registry and database, ensuring the agent sees the same data as the developer.
- **Intent-based Naming**: Reveal intent, not implementation (`calculateUserRiskScore` vs `get_api_data`).
- **Sustainable Engineering**: Every file starts with `ABOUTME` headers. Specification is the contract between human intent and AI implementation.

## Project Structure

- `multi_agent_investment.py`: Core orchestrator and agent reasoning logic.
- `llm_client.py`: Transport abstraction layer for LLM providers.
- `internal_configs.py`: Centralized prompt templates and tool schemas.
- `agent-definition-files/`: Markdown personas for specialized agents.
- `tests/`:
  - `test_model_config.py`: Single source of truth for test parameters.
  - `test_mock_workflow.py`: End-to-end integration test.
  - `agent-defs/`: Simplified agent personas for testing.

---

_This README serves as the primary context contract for AI assistants entering the codebase. Design intent is prioritized over implementation details._
