# Multi-Agent Investment Research System

A sophisticated coordination system for automated investment research. It leverages a multi-agent, synthesis-driven iterative architecture to provide high-conviction investment theses using stateful LLM agents and the Model Context Protocol (MCP).

## Recent Progress & Milestones (v1.6)

- **Finviz Scraper Integration**: Implemented `finviz_scraper.py` using **Crawl4AI v0.8**. The system now fetches high-fidelity market data and stock profiles directly into the Quantitative Agent's context.
- **Async Crawl Orchestration**: Adapted to the new v0.8 async task-queue model with a deterministic polling and backoff mechanism for robust data extraction.
- **Authenticated Service Bridge**: Implemented `Bearer` token authentication and internal Docker networking for the Crawl4AI service, ensuring secure and low-latency communication between research agents and the scraper.

## Web Scraping Implementation Findings

The integration of `crawl4ai` yielded several critical architectural insights:

1. **Async Task Queue (v0.8 API)**: Unlike previous synchronous versions, Crawl4AI v0.8 uses an asynchronous model where `/crawl` returns a `task_id` immediately. The orchestrator must poll `/task/{task_id}` until completion. The `FinvizScraper` implements this via a persistent `httpx` session with a backoff polling loop.
2. **Configuration Surface Area**: Attempting to pass complex `crawler_config` keys (like `wait_for`, `magic_mode`, or `remove_overlay_elements`) caused silent failures in headless environments. The most resilient pattern is providing a plain `{}` config, allowing the service's internal defaults to optimize the extraction.
3. **Internal Container Networking**: By standardizing on the Docker Compose service name (`http://crawl4ai:11235`) in `.env`, the system bypasses `host.docker.internal` overhead and resolves directly via the internal bridge network.

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
- **Enhanced Integration Testing**: Implemented `tests/test_mock_workflow.py` which executes a full research cycle using a local LLM and real MCP tool bridges.
- **Finviz Intelligence**: Scraper component using `crawl4ai` for deep extraction of market snapshots.

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

## Configuration Management

`internal_configs.py` is the centralized "Command Center" for the system. While security-sensitive keys are loaded from `.env`, all logic for provider routing and endpoint mapping resides here.

### Provider/Model/Endpoint Mapping

To change your preferences, update the following in `internal_configs.py`:

- **Change Provider**: Update `LLM_PROVIDER` (Line 22).
  - Set to `"openai"` to use the SDK path.
  - Set to `"openrouter"` to use the raw HTTP path.
  - Set to `"local"` for local model runners.
- **Change Model**: Update `PRIMARY_MODEL` (Line 19). This is passed directly to the active provider.
- **Change Endpoints**:
  - For local: Update `LOCAL_LLM_URL` (Line 23).
  - For production: Update `OPENROUTER_BASE_URL` or `OPENAI_CHAT_ENDPOINT`.

### How it works with `getLlmClient`

The `ResearchOrchestrator` uses the `getLlmClient` factory (from `llm_client.py`) to initialize the agent's brains. This factory is **URL-conscious**:

1. It reads the `provider` type and maps it to the correct implementation class.
2. It automatically **normalizes URLs** (e.g., stripping or appending `/chat/completions`) so that the user never has to worry about the specific endpoint requirements of each SDK or provider.
3. This decoupling allows the orchestrator to remain "blind" to the underlying transport while `internal_configs.py` provides the high-level routing instructions.

For a deeper dive into running local models, see [local_llm_guide.md](./local_llm_guide.md).

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
