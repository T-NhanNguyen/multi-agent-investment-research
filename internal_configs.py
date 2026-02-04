# ABOUTME: Centralized configurations for the multi-agent system.
# ABOUTME: Contains tool definitions, prompt templates, and output formats.

import os
from dataclasses import dataclass
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

    def validate(self):
        """Strict validation of required environment variables"""
        missing_vars = []
        if not self.OPENROUTER_API_KEY:
            missing_vars.append("OPENROUTER_API_KEY")
        if not self.PRIMARY_MODEL:
            missing_vars.append("MODEL_NAME")
        if not self.GRAPHRAG_REGISTRY_DIR:
            missing_vars.append("GRAPHRAG_REGISTRY_DIR")
        if not self.GRAPHRAG_PROJECT_PATH:
            missing_vars.append("GRAPHRAG_PROJECT_PATH")
            
        if missing_vars:
            error_msg = (
                "\n" + "!" * 50 + "\n"
                "CRITICAL ERROR: Environment Configuration Incomplete\n"
                f"Missing variables: {', '.join(missing_vars)}\n"
                "Please check your .env file and ensure these are set.\n"
                "!" * 50 + "\n"
            )
            raise ValueError(error_msg)

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
{original_analysis}

Query: {question}

Apply {specialization} domain expertise to respond.
"""

# Template for Phase 2 synthesis
SYNTHESIS_INPUT_TEMPLATE = """
Qualitative Analysis:
{qual_analysis}

Quantitative Analysis:
{quant_analysis}"""

# Questions for Phase 3 recursive clarification
QUAL_RECURSIVE_QUESTION = "Identify three material structural risks. Rank by impact probability and severity."
QUANT_RECURSIVE_QUESTION = "Assess metric reliability: stability indicators vs growth projections. State confidence bounds."

# Template for Phase 4 final consolidation
FINAL_CONSOLIDATION_TEMPLATE = """
Initial Synthesis:
{initial_synthesis}

Structural Risk Assessment:
{qual_clarification}

Quantitative Confidence:
{quant_clarification}"""

# Template for Momentum Analysis
MOMENTUM_CONSOLIDATION_TEMPLATE = """
Qualitative Intelligence:
{qual_analysis}

Quantitative Data:
{quant_analysis}

Recursive Risk Insights:
{qual_clarification}

Recursive Confidence Data:
{quant_clarification}
"""

# --- Output Templates ---

MARKDOWN_REPORT_TEMPLATE = """> Prompt: {query}

## Qualitative Analysis
{qual_analysis}

### Risks
{qual_clarification}

## Quantitative Analysis
{quant_analysis}

### Confidence
{quant_clarification}

## Final Recommendation
{final_recommendation}
"""

MOMENTUM_REPORT_SECTION = """
# Momentum Trade Analysis
{momentum_analysis}
"""
