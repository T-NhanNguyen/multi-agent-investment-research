# ABOUTME: strict abstraction layer for LLM interactions.
# ABOUTME: Handles network transport, retries, and error handling, decoupling Agents from HTTP logic.

import json
import logging
import httpx
import anyio
from typing import Dict, List, Optional
from abc import ABC, abstractmethod

# Configure logging
logger = logging.getLogger(__name__)

class ILlmClient(ABC):
    """Interface for LLM interactions to enable swapping real/mock implementations."""
    
    @abstractmethod
    async def chatCompletion(self, model: str, messages: List[Dict], tools: Optional[List[Dict]] = None) -> Dict:
        pass

class LocalLlmClient(ILlmClient):
    """Client for local LLM interactions using OpenAI-compatible API format (Ollama/Docker Model Runner)."""
    
    def __init__(self, baseUrl: str, model: str, temperature: float = 0.1, maxTokens: int = 2048):
        """
        Initialize LLM client with baseUrl and model name.
        baseUrl should be the root (e.g., http://localhost:11434)
        """
        self.baseUrl = baseUrl.rstrip('/')
        self.model = model
        self.temperature = temperature
        self.maxTokens = maxTokens
        
        logger.info(f"LocalLlmClient initialized: {self.baseUrl} using {self.model}")

    async def chatCompletion(self, model: str, messages: List[Dict], tools: Optional[List[Dict]] = None) -> Dict:
        """
        Execute a chat completion request using OpenAI-compatible /v1/chat/completions endpoint.
        Includes a retry loop for 503 errors (common during local model loading).
        """
        endpoint = f"{self.baseUrl}/v1/chat/completions"
        
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.maxTokens
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        max_retries = 3
        retry_delay = 10 # seconds

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=600.0) as client:
                    response = await client.post(endpoint, json=payload)
                    
                    if response.status_code == 503:
                        logger.warning(f"Local LLM is still loading model (503). Retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})")
                        await anyio.sleep(retry_delay)
                        continue
                        
                    response.raise_for_status()
                    return response.json()
                    
            except httpx.HTTPStatusError as httpError:
                if httpError.response.status_code == 503:
                    continue # Already handled above, but safe guard
                logger.error(f"Local LLM API Error {httpError.response.status_code}: {httpError.response.text}")
                raise
            except Exception as unexpectedError:
                logger.error(f"Local LLM Unexpected failure: {unexpectedError}")
                raise
        
        raise RuntimeError(f"Local LLM failed to load model after {max_retries} attempts.")

class OpenRouterClient(ILlmClient):
    """Production client for OpenRouter API."""
    
    def __init__(self, apiKey: str, baseUrl: str, maxRetries: int = 3, backoffCap: int = 60):
        self.apiKey = apiKey
        self.baseUrl = baseUrl
        self.maxRetries = maxRetries
        self.backoffCap = backoffCap

    async def chatCompletion(self, model: str, messages: List[Dict], tools: Optional[List[Dict]] = None) -> Dict:
        """
        Execute a chat completion request with built-in retry logic and rate limit handling.
        """
        payload = {
            "model": model,
            "messages": messages
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        for retryAttempt in range(self.maxRetries):
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    logger.debug(f"Requesting LLM: {model} (Attempt {retryAttempt + 1})")
                    
                    response = await client.post(
                        self.baseUrl,
                        headers={
                            "Authorization": f"Bearer {self.apiKey}",
                            "Content-Type": "application/json"
                        },
                        json=payload
                    )
                    response.raise_for_status()
                    return response.json()
                    
            except httpx.HTTPStatusError as httpError:
                if httpError.response.status_code == 429:
                    retryAfter = httpError.response.headers.get("Retry-After")
                    try:
                        backoffSeconds = int(retryAfter) if retryAfter else min(2 ** retryAttempt, self.backoffCap)
                    except ValueError:
                        backoffSeconds = 60
                    
                    logger.warning(f"Rate limited (429). Backing off for {backoffSeconds}s.")
                    await anyio.sleep(backoffSeconds)
                else:
                    logger.error(f"API Error {httpError.response.status_code}")
                    if retryAttempt == self.maxRetries - 1: raise
                    await anyio.sleep(2 ** retryAttempt)
                    
            except Exception as unexpectedError:
                logger.error(f"Unexpected failure: {unexpectedError}")
                if retryAttempt == self.maxRetries - 1: raise
                await anyio.sleep(2 ** retryAttempt)
                
        raise RuntimeError(f"Failed to get LLM response after {self.maxRetries} attempts.")

def getLLMClient(
    provider: str, 
    model: str, 
    apiKey: Optional[str] = None, 
    baseUrl: Optional[str] = None,
    backoffCap: int = 60
) -> ILlmClient:
    """Factory function to instantiate the correct LLM client based on provider."""
    provider = provider.lower()
    if provider == "local":
        return LocalLlmClient(
            baseUrl=baseUrl or "http://localhost:11434", 
            model=model
        )
    else:
        return OpenRouterClient(
            apiKey=apiKey or "", 
            baseUrl=baseUrl or "https://openrouter.ai/api/v1/chat/completions",
            backoffCap=backoffCap
        )
