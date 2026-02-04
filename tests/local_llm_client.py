# Local LLM Client - Entity and relationship extraction via Docker-hosted or OpenRouter models.
import json
import re
import logging
import uuid
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

import httpx
from tests.test_model_config import settings
from openai import OpenAI

logger = logging.getLogger(__name__)

# Enable httpx logging for LLM requests (matches embedding_provider behavior)
logging.getLogger("httpx").setLevel(logging.INFO)


# Result Dataclass
@dataclass
class ExtractionResult:
    # Result from entity/relationship extraction.
    entities: List[Entity]
    relationships: List[Relationship]
    rawResponse: str
    success: bool
    errorMessage: Optional[str] = None


class LocalLLMClient:
    # Client for local LLM extraction using OpenAI-compatible API format (Ollama/Docker Model Runner).
    
    def __init__(self, baseUrl: Optional[str] = None, model: Optional[str] = None):
        # Initialize LLM client with optional baseUrl and model name.
        self.baseUrl = baseUrl or settings.LLM_URL
        self.model = model or settings.LLM_MODEL
        self.temperature = settings.LLM_TEMPERATURE
        self.maxTokens = settings.LLM_MAX_TOKENS
        self.maxEntities = settings.MAX_ENTITIES_PER_CHUNK
        self.maxRelationships = settings.MAX_RELATIONSHIPS_PER_CHUNK
        
        logger.info(f"LLM client initialized: {self.baseUrl} using {self.model}")
    
    def _callLLM(self, prompt: str, taskDescription: str = "LLM request") -> Tuple[str, Optional[str]]:
        # Make a chat completion request to the LLM. Returns (response_text, error_message).
        # Docker Model Runner uses OpenAI-compatible /v1/chat/completions endpoint
        endpoint = f"{self.baseUrl}/v1/chat/completions"
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": settings.LLM_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature,
            "max_tokens": self.maxTokens,
            "num_ctx": settings.LLM_CONTEXT_LENGTH  # Explicit context window for llama.cpp
        }
        
        # Diagnostic logging: estimate token count (rough: 4 chars per token)
        systemPromptLen = len(settings.LLM_SYSTEM_PROMPT)
        promptLen = len(prompt)
        estimatedInputTokens = (systemPromptLen + promptLen) // 4
        logger.debug(f"LLM request: ~{estimatedInputTokens} input tokens, max_tokens={self.maxTokens}, num_ctx={settings.LLM_CONTEXT_LENGTH}")
        
        try:
            with httpx.Client(timeout=600.0) as client:
                response = client.post(endpoint, json=payload)
                response.raise_for_status()
                
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                return content, None
                
        except httpx.TimeoutException:
            error = f"LLM request timed out after 600s"
            logger.error(f"Error: {error}. Prompt snippet: {prompt[:500]}...")
            return "", error
        except httpx.HTTPStatusError as exc:
            error = f"LLM API error: {exc.response.status_code}: {exc.response.text}"
            logger.error(f"Error: {error}. Prompt snippet: {prompt[:500]}...")
            return "", error
        except httpx.ConnectError as exc:
            error = f"Cannot connect to LLM at {self.baseUrl}"
            logger.error(f"Error: {error}. Prompt snippet: {prompt[:500]}...")
            return "", error
        except Exception as exc:
            error = f"LLM request failed: {exc}"
            logger.error(f"[ERROR] {error}. Prompt snippet: {prompt[:500]}...")
            return "", error

def getLLMClient(baseUrl: Optional[str] = None, model: Optional[str] = None) -> LocalLLMClient:
    # Factory for general LLM client (entities, summarization, pruning).
    provider = settings.RELATIONSHIP_PROVIDER
    
    if provider == "openrouter":
        from llm_client import OpenRouterClient # Late import to avoid cycles or missing imports
        return OpenRouterClient(model=model)
    
    return LocalLLMClient(baseUrl, model)
