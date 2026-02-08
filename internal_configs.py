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
    
    # Model Selection
    PRIMARY_MODEL: str = os.getenv("MODEL_NAME", "z-ai/glm-4.5-air:free")
    WEB_SEARCH_MODEL: str = os.getenv("WEB_SEARCH_MODEL", os.getenv("MODEL_NAME", "z-ai/glm-4.5-air:free"))
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openrouter").lower()
    LOCAL_LLM_URL: str = os.getenv("LOCAL_LLM_URL", "http://host.docker.internal:12434").strip()
    
    # Operational Parameters
    MAX_RETRIES: int = 3
    RATE_LIMIT_BACKOFF_CAP: int = 120  # seconds
    PHASE_THROTTLE_SECONDS: float = 1.0
    OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "./output")
    
    # Docker & MCP Configuration
    FINANCE_TOOLS_IMAGE: str = "finance-tools"
    GRAPHRAG_IMAGE: str = "graphrag-llamaindex"
    GRAPHRAG_NODE_MODULES_VOLUME: str = "graphrag_node_modules"
    GRAPHRAG_DEFAULT_DB: str = "investment-analysis"
    
    # Path Configuration (GraphRAG)
    GRAPHRAG_REGISTRY_DIR: str = os.getenv("GRAPHRAG_REGISTRY_DIR", "").strip()
    GRAPHRAG_PROJECT_PATH: str = os.getenv("GRAPHRAG_PROJECT_PATH", "").strip()
    GRAPHRAG_DATABASE: str = os.getenv("GRAPHRAG_DATABASE", "investment-analysis").strip()
    
    # Defaults
    DEFAULT_INVESTMENT_QUERY: str = "Analyze Tesla (TSLA)"
    DEFAULT_RESEARCH_MODE: str = os.getenv("DEFAULT_MODE", "fundamental").strip().lower()
    RESEARCH_MODES: list = field(default_factory=lambda: ["fundamental", "momentum", "all"])

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
                "max_results": {
                    "type": "integer",
                    "description": "Number of results to fetch",
                    "default": 3
                }
            },
            "required": ["query"]
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
