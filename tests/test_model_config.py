# Test Configuration - Settings for local LLM integration tests.
from pydantic_settings import BaseSettings

class TestSettings(BaseSettings):
    """Runtime configuration for local LLM tests."""
    # Local LLM Configuration (Docker Model Runner / Ollama)
    LLM_URL: str = "http://host.docker.internal:12434"
    LLM_MODEL: str = "ai/granite-4.0-micro:latest"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 2048
    LLM_CONTEXT_LENGTH: int = 32768
    LLM_SYSTEM_PROMPT: str = "You are a helpful research assistant."
    
    # Provider Logic (Options: 'local', 'openrouter')
    RELATIONSHIP_PROVIDER: str = "local"
    
    # Tool Config
    FINANCE_TOOLS_IMAGE: str = "finance-tools"
    GRAPHRAG_IMAGE: str = "graphrag-llamaindex"
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = TestSettings()
