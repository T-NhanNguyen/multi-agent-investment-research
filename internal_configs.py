# ABOUTME: Centralized configurations for the multi-agent system.
# ABOUTME: Contains tool definitions, prompt templates, and output formats.

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load environment variables early to ensure AppConfig picks them up
load_dotenv()

@dataclass
class AppConfig:
    """Core operational parameters and environment-backed configurations"""
    # API Credentials
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "").strip()
    OPENAI_API_KEY: str = OPENROUTER_API_KEY
    
    # Model Selection
    PRIMARY_MODEL: str = os.getenv("MODEL_NAME", "z-ai/glm-4.5-air:free")
    WEB_SEARCH_MODEL: str = os.getenv("WEB_SEARCH_MODEL", os.getenv("MODEL_NAME", "z-ai/glm-4.5-air:free"))
    INTEGRATION_TEST_MODEL: str = os.getenv("INTEGRATION_TEST_MODEL", "z-ai/glm-4.5-air:free")
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openrouter").lower()
    LOCAL_LLM_URL: str = os.getenv("LOCAL_LLM_URL", "http://host.docker.internal:12434").strip()
    
    # Operational Parameters
    MAX_RETRIES: int = 3
    MAX_TOOL_CYCLES: int = 15
    RATE_LIMIT_BACKOFF_CAP: int = 5  # seconds
    PHASE_THROTTLE_SECONDS: float = 1.0
    OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "./output")
    
    # Docker & MCP Configuration
    FINANCE_TOOLS_IMAGE: str = os.getenv("FINANCE_TOOLS_IMAGE", "finance-tools-finance-tools")
    GRAPHRAG_IMAGE: str = "graphrag-llamaindex"
    GRAPHRAG_NODE_MODULES_VOLUME: str = "graphrag_node_modules"
    GRAPHRAG_DEFAULT_DB: str = "investment-analysis"
    
    # Path Configuration (GraphRAG)
    GRAPHRAG_REGISTRY_DIR: str = os.getenv("GRAPHRAG_REGISTRY_DIR", "").strip()
    GRAPHRAG_PROJECT_PATH: str = os.getenv("GRAPHRAG_PROJECT_PATH", "").strip()
    GRAPHRAG_DATABASE: str = os.getenv("GRAPHRAG_DATABASE", "investment-analysis").strip()
    
    # API Endpoints
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_CHAT_ENDPOINT: str = f"{OPENROUTER_BASE_URL}/chat/completions"
    OPENROUTER_RESPONSES_ENDPOINT: str = f"{OPENROUTER_BASE_URL}/responses"
    OPENAI_CHAT_ENDPOINT: str = "https://api.openai.com/v1"
    
    # Defaults
    DEFAULT_INVESTMENT_QUERY: str = "Analyze Tesla (TSLA)"
    DEFAULT_RESEARCH_MODE: str = os.getenv("DEFAULT_MODE", "fundamental").strip().lower()
    RESEARCH_MODES: list = field(default_factory=lambda: ["fundamental", "momentum", "all"])
    
    # Synthesis Orchestration
    MAX_SYNTHESIS_ITERATIONS: int = 1
    PHASE_THROTTLE_SECONDS: float = 1.0

    def verifyConfiguration(self):
        """
        Strict validation of required environment variables.
        Ensures the system fails fast if the operational bedrock is missing.
        """
        missingVars = []
        if not self.OPENROUTER_API_KEY:
            missingVars.append("OPENROUTER_API_KEY")
        if not self.PRIMARY_MODEL:
            missingVars.append("MODEL_NAME")
        if not self.GRAPHRAG_REGISTRY_DIR:
            missingVars.append("GRAPHRAG_REGISTRY_DIR")
        if not self.GRAPHRAG_PROJECT_PATH:
            missingVars.append("GRAPHRAG_PROJECT_PATH")
            
        if missingVars:
            errorReport = (
                "\n" + "!" * 50 + "\n"
                "CRITICAL ERROR: Environment Configuration Incomplete\n"
                f"Missing variables: {', '.join(missingVars)}\n"
                "Please check your .env file and ensure these are set.\n"
                "!" * 50 + "\n"
            )
            raise ValueError(errorReport)

# Global config instance
config = AppConfig()


# --- Tool Definitions ---

WEB_SEARCH_TOOL_DEFINITION = {
    "web_search": {
        "name": "web_search",
        "description": "DELEGATE ONLY: Ask the Web Research Specialist to find recent news, "
                       "announcements, or live data not in your context. Provide a specific query.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Specific search query (e.g., 'IREN latest news January 2026')"
                },
                "search_rationale": {
                    "type": "string",
                    "description": "Critical: Why is this search necessary? What specific intelligence gap are you filling that is NOT in your existing context?"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Number of results to fetch",
                    "default": 3
                }
            },
            "required": ["query", "search_rationale"]
        }
    }
}

# --- Prompt Templates ---

# Template for follow-up questions in Agent class
FOLLOW_UP_PROMPT_TEMPLATE = """
Reference Analysis:
{originalAnalysis}

Query: {question}

Apply {specialization} domain expertise to respond.
"""

# Template for Phase 2 synthesis
SYNTHESIS_INPUT_TEMPLATE = """
Qualitative Analysis:
{qualAnalysis}

Quantitative Analysis:
{quantAnalysis}"""

# Questions for Phase 3 recursive clarification
QUAL_RECURSIVE_QUESTION = "Identify three material structural risks. Rank by impact probability and severity."
QUANT_RECURSIVE_QUESTION = "Assess metric reliability: stability indicators vs growth projections. State confidence bounds."

# Template for consolidating multiple intelligence strands (Fundamental or Momentum)
AGENTS_INFORMATION_CONTEXT_TEMPLATE = """
Qualitative Intelligence:
{qualAnalysis}

Quantitative Data:
{quantAnalysis}

Recursive Risk Insights:
{qualClarification}

Recursive Confidence Data:
{quantClarification}

Initial Synthesis:
{initialSynthesis}
"""

# --- Synthesis-Driven Iterative Templates ---

# Template for initial query analysis
SYNTHESIS_INITIAL_PROMPT_TEMPLATE = """
Analyze this investment query and determine what information you need from the specialized agents (Qualitative and Quantitative).

Query: {investmentQuery}

Your goal is to identify information gaps and generate targeted requests.
Follow the structured output format defined in your system prompt (Mode 1).
"""

# Template for subsequent iterations
SYNTHESIS_ITERATION_PROMPT_TEMPLATE = """
Specialist Responses (Iteration {iteration}):

## Qualitative Agent:
{qualResponse}

## Quantitative Agent:
{quantResponse}

---

Evaluate these results. If significant gaps remain, request targeted follow-ups.
If you have enough information for a final thesis, signal completion by outputting "Done" or "There is nothing else needed".

Confidence Threshold: If you are 80%+ confident you can derive an answer from existing data, signal completion.
"""

# Template for final consolidated synthesis
SYNTHESIS_FINAL_THESIS_TEMPLATE = """
Research complete. Produce the final investment decision document using all the data we've gathered across our entire conversation.

Follow the writing style guide and templates in your system prompt (Mode 3) and `synthesis_writing_guide.md`.
"""

# --- Output Templates ---

MARKDOWN_REPORT_TEMPLATE = """> Prompt: {query}

## Qualitative Analysis
{qualAnalysis}

### Risks
{qualClarification}

## Quantitative Analysis
{quantAnalysis}

### Confidence
{quantClarification}

## Final Recommendation
{finalRecommendation}
"""

MOMENTUM_REPORT_SECTION = """
# Momentum Trade Analysis
{momentumAnalysis}
"""
