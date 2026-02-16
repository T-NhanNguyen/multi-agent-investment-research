# Multi-Agent Investment Research System

A sophisticated coordination system for automated investment research. It leverages a multi-agent, synthesis-driven iterative architecture to provide high-conviction investment theses using stateful LLM agents and the Model Context Protocol (MCP).

## Recent Progress & Milestones (v1.3)

- **Synthesis-Driven Iterative Research**: Pivot away from parallel-first exploration. The research cycle now starts with the **Synthesis Agent** analyzing the user query to identify specific information gaps and generating targeted requests for specialized agents.
- **Stateful Context management**: Agents now maintain an in-memory `messageHistory` (persistent conversation state) throughout a research session. This eliminates the need for the orchestrator to repeat the full conversation history in every turn, allowing the LLM to manage its own memory and significantly reducing redundant prompt bloat.
- **Orchestrator-Led Logic**: The Python orchestrator handles completion detection (via regex for "Done" signals) and triggers the final synthesis phase with a dedicated call, leveraging the `synthesis_writing_guide.md` for consistent narrative style.
- **Deterministic Shutdown & Task Safety**: Resolved critical `anyio` task boundary violations during MCP cleanup. Implemented a `connectAll()` pre-connection protocol in the main orchestrator task. This ensures context managers (like `stdio_client`) are entered and exited within the same `asyncio.Task`, even when tool-consuming specialist agents are executed in parallel via `asyncio.gather`.
- **Resilient Content Recovery**: The `Agent` class now implements an **Active Retry** mechanism for empty LLM responses. This prevents premature session termination due to transient provider failures or extreme context-length pressure.
- **Decoupled Stability Controls**: Introduced `MAX_TOOL_CYCLES` (15) to ensure agents have sufficient "breathing room" for complex internal research tasks (ticker resolution, etc.), independent of broader request retries.

## Recent Progress & Milestones (v1.2)

- **Agentic Tool Call Self-Correction**: Implemented a robust loop for handling malformed LLM tool arguments. If an agent produces invalid JSON, the system feeds the parse error back into the conversation history, allowing the LLM to autonomously correct its output without human intervention.
- **Deterministic Token Accounting**: Redesigned the monitoring architecture to utilize OpenRouter's native `prompt_tokens` and `completion_tokens` receipts. The system now tracks consumption per-phase, ensuring $100\%$ accuracy in production billing metrics.
- **Precision Test Metrics**: Integrated `tiktoken` into the `MockTokenTrackingLLM` within `tests/test_output_pruning.py`. This replaces character-length heuristics with deterministic token counts, validating that the pruning system achieves **>50% reduction** in input context overhead.
- **Improved Monitoring Observability**: The `MonitoringState` now captures `pruning_events` and utilizes downstream consumption multipliers to estimate real-world token savings across compounding research phases.

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
  - `monitoring_wrapper.py`: Non-invasively instruments the multi-agent system. It captures native OpenRouter receipts, tracks per-phase token consumption buckets, and logs `pruning_events` for efficiency analysis.
  - `api_server.py`: A FastAPI instance providing a real-time status endpoint (`/api/status`) and detailed optimization summaries.
- **Agentic Resilience**: `Agent.performResearchTask` implements a self-correction loop (`MAX_TOOL_CYCLES`) that enables LLMs to recover from its own hallucinated tool schemas or malformed JSON arguments by providing corrective feedback in the context.
- **Stateful Context Management**: The `Agent` class maintains a `self.messageHistory` list that persists across calls within a session. The orchestrator calls `resetHistory()` at the start of new sessions to ensure a clean state.
- **Synthesis-Driven Orchestration**: The workflow is now iterative:
  1. **Synthesis Agent** analyzes query and creates targeted requests.
  2. **Specialists** (Qual/Quant) fulfill requests in parallel.
  3. **Synthesis Agent** evaluates results and either requests more info or signals completion ("Done").
  4. **Orchestrator** triggers the final Mode 3 synthesis upon completion signal.
- **Deterministic Cleanup Pattern**: To avoid `RuntimeError: Attempted to exit cancel scope in a different task`, the system adheres to a strict "Pre-Connect" protocol:
  - `ResearchOrchestrator.connectAll()` is called in the main task context before any parallel specialist execution.
  - This locks the `anyio.CancelScope` to the primary execution task, making the `finally` block cleanup safe.

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

## Output Pruning Middleware

`output_pruner.py` reduces inter-agent token usage by stripping noise from LLM outputs before they are passed to downstream agents. Pruning is applied at **orchestration boundaries only** — each agent produces its full output, and the orchestrator decides what to forward.

**What gets stripped:**

- Thinking preambles (`"I'll conduct..."`, `"Let me check..."`)
- Internal workflow headers (`"## Phase 1:"`, `"## Step 1:"`)
- Standalone separator lines (`---`)

**What is preserved:**

- All data points, metrics, conclusions, and named entities
- Lines > 200 chars (safety heuristic against false-positive stripping)
- Raw outputs in `researchStateMap` for final report generation

**Integration points** in `multi_agent_investment.py`:

- Phase 1 → Phase 2 (Synthesis)
- Phase 1 → Phase 3 (Clarification)
- Phase 2/3 → Phase 4 (Consolidation)
- Recursive `provideRecursiveAnalysis` calls

**Verification:**
The system is verified via `tests/test_output_pruning.py`, which performs a deterministic A/B comparison (RAW vs PRUNED) using `tiktoken`. It consistently demonstrates a **>50% token reduction** in context-heavy multi-agent workflows.

## Project Structure

- `multi_agent_investment.py`: Core orchestrator, stateful `Agent` logic, and synthesis refinement loop.
- `llm_client.py`: Transport abstraction layer for LLM providers.
- `internal_configs.py`: Centralized prompt templates, `MAX_TOOL_CYCLES`, and tool schemas.
- `output_pruner.py`: Stateless utility for pruning LLM noise at inter-agent handoffs.
- `monitoring_wrapper.py`: Non-invasive instrumentation for token usage and phase tracking.
- `api_server.py`: FastAPI real-time status endpoint.
- `agent-definition-files/`:
  - `synthesis_agent.md`: The "Orchestrator Brain" managing research gaps.
  - `synthesis_writing_guide.md`: Style bedrock and templates for final investment documents.
  - `qualitative_agent.md` & `quantitative_agent.md`: On-demand specialized providers.
- `tests/`:
  - `test_model_config.py`: Single source of truth for test parameters.
  - `test_mock_workflow.py`: End-to-end integration test.
  - `test_output_pruning.py`: Token reduction verification (RAW vs PRUNED scenarios).
  - `agent-defs/`: Simplified agent personas for testing.

---

_This README serves as the primary context contract for AI assistants entering the codebase. Design intent is prioritized over implementation details._
