# Multi-Agent Investment Research System

A sophisticated coordination system for automated investment research. It leverages a multi-agent, synthesis-driven iterative architecture to provide high-conviction investment theses using stateful LLM agents and the Model Context Protocol (MCP).

## Recent Progress & Milestones (v1.5)

- **Architecture Hardening**: Decoupled the `monitoring_wrapper` from brittle HTTP monkey-patching. It now exclusively reads structured `lastResponse` data from agents, restoring a clean separation of concerns.
- **Provider-Agnostic Factory**: Refactored `getLlmClient` to handle URL normalization automatically across Local, OpenAI (SDK), and OpenRouter providers.
- **Backward-Compatible Usage Tracking**: Added `_normalizeUsage` protocol in the client layer to ensure consistent token metrics regardless of the backend (SDK vs raw REST).
- **Tech Debt Cleanup**: Removed obsolete test configurations (`test_model_config.py`) and legacy extraction clients (`local_llm_client.py`), centralizing all research configuration in `internal_configs.py`.

## Recent Progress & Milestones (v1.4)

- **SDK-Based LLM Integration**: Migrated the `OpenAIClient` to the official `openai` Python SDK. This provides more robust connection pooling and native compatibility with OpenRouter's V1 API.
- **Structured "ChatResponse" Architecture**: Replaced raw dictionary responses with a structured `ChatResponse` dataclass. This unifies response formats across providers and provides a much more intuitive interface for developers (e.g., `response.content`, `response.usageSummary`).
- **Automated Reasoning Extraction**: The client now automatically detects and extracts "thinking" or "reasoning" content from o1, o3, and DeepSeek models, keeping the final output clean while preserving the agent's thought process for debugging.
- **Enhanced Observability**: Integrated deep response logging that provides a human-readable summary of token usage and reasoning on every LLM turn.

## Recent Progress & Milestones (v1.3)

- **Synthesis-Driven Iterative Research**: Pivot away from parallel-first exploration. The research cycle now starts with the **Synthesis Agent** analyzing the user query to identify specific information gaps and generating targeted requests for specialized agents.
- **Stateful Context management**: Agents now maintain an in-memory `messageHistory` throughout a research session. This eliminates the need for the orchestrator to repeat the full conversation history in every turn.
- **Deterministic Shutdown & Task Safety**: Resolved critical `anyio` task boundary violations during MCP cleanup. Implemented a `connectAll()` pre-connection protocol in the main orchestrator task.
- **Resilient Content Recovery**: The `Agent` class now implements an **Active Retry** mechanism for empty LLM responses. This prevents premature session termination due to transient provider failures or extreme context-length pressure.

## Architecture

The system follows a modular, agentic design pattern:

- **Orchestration**: `ResearchOrchestrator` (in `multi_agent_investment.py`) manages the 4-phase research workflow.
- **Agent Engine**: `agent_engine.py` contains the core `Agent` logic, state management (`messageHistory`), and `McpToolProvider` integration. This layer is decoupled from specific LLM vendors.
- **LLM Transport Layer**: `llm_client.py` provides an abstraction (`ILlmClient`) returning structured `ChatResponse` objects. Implementations include:
  - `OpenAIClient`: Primary SDK-based client for OpenRouter and OpenAI. Supports stateful history and reasoning extraction.
  - `LocalLlmClient`: Development-grade client for local model runners (Ollama, etc.).
  - `ChatResponse`: A unified container that separates **Thinking**, **Content**, and **Usage**.
- **Agent Specification**: Personas are defined as Markdown files in `agent-definition-files/`. These are parsed at runtime to build system prompts dynamically.
- **Observability**:
  - `monitoring_wrapper.py`: Non-invasively instruments the system by reading `agent.lastResponse`. It tracks per-phase token consumption and logs activity for the UI.
  - `api_server.py`: A FastAPI instance providing a real-time status endpoint (`/api/status`).

## Setup and Development

### Prerequisites

- **Docker Desktop**: Required for MCP tool containers and `docker.sock` access.
- **OpenRouter API Key**: Set in `.env`.
- **Local LLM Runner**: (Optional) Ollama or Docker Model Runner on `host.docker.internal:12434`.

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

# Integration Testing (Mocked LLM)
docker-compose run --rm investment-research python tests/test_mock_workflow.py

# Live Stateful Verification
docker-compose run --rm investment-research python tests/test_openai_stateful.py
```

## Testing Procedures

The project adheres to **Test-Driven Development (TDD)**:

1. **Mock Workflow**: `tests/test_mock_workflow.py` verifies phase transitions and state management without using real LLM credits.
2. **Stateful Integration**: `tests/test_openai_stateful.py` validates multi-turn context preservation and usage tracking using the real OpenAI SDK.
3. **Tool Isolation**: `tests/test_output_pruning.py` verifies strict tool boundaries and token reduction heuristics.

## Key Conventions and Patterns

- **Bridge to Local Data**: Tools like GraphRAG are executed via Docker with volume mounts, ensuring parity between agent and developer environments.
- **Sustainable Engineering**: Every file starts with `ABOUTME` headers. Specification is the contract between human intent and AI implementation.

## Project Structure

- `multi_agent_investment.py`: Main entry point and research workflow orchestration.
- `agent_engine.py`: Core agent abstractions, tools provider, and message history logic.
- `llm_client.py`: Multi-provider LLM transport layer and `ChatResponse` definitions.
- `internal_configs.py`: Centralized source of truth for prompts, model names, and tool schemas.
- `monitoring_wrapper.py`: Decoupled instrumentation for usage tracking and UI updates.
- `output_pruner.py`: Utility for stripping boilerplate during inter-agent context handoffs.
- `agent-definition-files/`: Markdown-based agent personas and writing guides.
- `tests/`: Comprehensive test suite (Mock, Integration, and Pruning).

---

_This README serves as the primary context contract for AI assistants entering the codebase. Design intent is prioritized over implementation details._
