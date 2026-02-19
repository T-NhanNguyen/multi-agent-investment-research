# ABOUTME: strict abstraction layer for LLM interactions.
# ABOUTME: Handles network transport, retries, and error handling, decoupling Agents from HTTP logic.

import logging
import anyio
import re
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx
from openai import AsyncOpenAI

# Configure logging
logger = logging.getLogger(__name__)

@dataclass
class ChatResponse:
    """
    ABOUTME: Structured container for LLM responses.
    ABOUTME: Unifies different provider formats and separates 'Thinking' from 'Content'.
    """
    id: str
    content: str
    role: str = "assistant"
    reasoning: Optional[str] = None
    toolCalls: Optional[List[Dict]] = None
    usage: Dict[str, int] = field(default_factory=dict)
    finishReason: Optional[str] = None

    @property
    def message(self) -> Dict[str, Any]:
        """Returns the standard message dict for history appending."""
        msg = {
            "role": self.role,
            "content": self.content
        }
        if self.toolCalls:
            msg["tool_calls"] = self.toolCalls
        if self.reasoning:
            msg["reasoning"] = self.reasoning
        return msg

    @property
    def usageSummary(self) -> str:
        """Friendly summary of token consumption."""
        if not self.usage:
            return "Usage unknown"
        
        promptTokens = self.usage.get("prompt_tokens", 0)
        completionTokens = self.usage.get("completion_tokens", 0)
        return f"Tokens: {promptTokens + completionTokens} (Prompt: {promptTokens}, Completion: {completionTokens})"

    def __str__(self) -> str:
        """Intuitive preview for console logging."""
        out = f"[{self.role.upper()} ID: {self.id}]"
        if self.reasoning:
            out += f"\nTHINKING: {self.reasoning[:150].strip()}..."
        out += f"\nCONTENT: {self.content[:300].strip()}..."
        if self.toolCalls:
            out += f"\nTOOLS: {len(self.toolCalls)} calls"
        out += f"\n{self.usageSummary}"
        return out

    # Backward compatibility for dict-style access in legacy orchestrators
    def __getitem__(self, key):
        if key == "choices":
            return [
                {
                    "message": self.message,
                    "finish_reason": self.finishReason
                }
            ]
        if key == "usage":
            return self.usage
        if key == "id":
            return self.id
        raise KeyError(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

class ILlmClient(ABC):
    """Interface for LLM interactions to enable swapping real/mock implementations."""
    
    @abstractmethod
    async def chatCompletion(self, model: str, messages: List[Dict], tools: Optional[List[Dict]] = None) -> ChatResponse:
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

    async def chatCompletion(self, model: str, messages: List[Dict], tools: Optional[List[Dict]] = None) -> ChatResponse:
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

        maxRetries = 3
        retryDelay = 10  # seconds

        for attempt in range(maxRetries):
            try:
                async with httpx.AsyncClient(timeout=600.0) as client:
                    response = await client.post(endpoint, json=payload)
                    
                    if response.status_code == 503:
                        logger.warning(
                            f"Local LLM still loading (503). "
                            f"Retrying in {retryDelay}s... (Attempt {attempt + 1}/{maxRetries})"
                        )
                        await anyio.sleep(retryDelay)
                        continue
                        
                    response.raise_for_status()
                    data = response.json()
                    
                    choice = data["choices"][0]
                    msg = choice["message"]
                    
                    return ChatResponse(
                        id=data.get("id", "local_id"),
                        content=msg.get("content", ""),
                        role=msg.get("role", "assistant"),
                        toolCalls=msg.get("tool_calls"),
                        usage=_normalizeUsage(data.get("usage", {})),
                        finishReason=choice.get("finish_reason")
                    )
            except Exception as exc:
                logger.error(f"Local LLM error (Attempt {attempt + 1}): {exc}")
                if attempt == maxRetries - 1:
                    raise
                await anyio.sleep(2)
        
        raise RuntimeError("Local LLM failed after maximum retries")

class OpenRouterClient(ILlmClient):
    """Production client for OpenRouter API."""
    
    def __init__(self, apiKey: str, baseUrl: str, maxRetries: int = 3, backoffCap: int = 60):
        self.apiKey = apiKey
        self.baseUrl = baseUrl
        self.maxRetries = maxRetries
        self.backoffCap = backoffCap

    async def chatCompletion(self, model: str, messages: List[Dict], tools: Optional[List[Dict]] = None) -> ChatResponse:
        payload = {
            "model": model,
            "messages": messages
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        for attempt in range(self.maxRetries):
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    response = await client.post(
                        self.baseUrl,
                        headers={
                            "Authorization": f"Bearer {self.apiKey}", 
                            "Content-Type": "application/json"
                        },
                        json=payload
                    )
                    response.raise_for_status()
                    data = response.json()
                    choice = data["choices"][0]
                    msg = choice["message"]
                    
                    return ChatResponse(
                        id=data.get("id"),
                        content=msg.get("content", ""),
                        role=msg.get("role", "assistant"),
                        toolCalls=msg.get("tool_calls"),
                        usage=_normalizeUsage(data.get("usage", {})),
                        finishReason=choice.get("finish_reason")
                    )
            except Exception as exc:
                logger.error(f"OpenRouterClient error (Attempt {attempt + 1}): {exc}")
                if attempt == self.maxRetries - 1:
                    raise
                await anyio.sleep(2 ** attempt)
                
        raise RuntimeError("OpenRouterClient failed after maximum retries")

class OpenAIClient(ILlmClient):
    """
    ABOUTME: Primary production client using OpenAI SDK over OpenRouter.
    ABOUTME: Automatically detects and extracts reasoning for capable models.
    """
    
    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, apiKey: str, baseUrl: str = OPENROUTER_BASE_URL, maxRetries: int = 3, backoffCap: int = 60):
        self.maxRetries = maxRetries
        self.backoffCap = backoffCap
        self._client = AsyncOpenAI(
            api_key=apiKey,
            base_url=baseUrl,
            default_headers={
                "HTTP-Referer": "https://github.com/multi-agent-investment-research",
                "X-Title": "Multi-Agent Investment Research"
            },
            max_retries=0  # We handle retries ourselves for full observability
        )
        logger.info(f"OpenAIClient (SDK) initialized pointing to {baseUrl}")

    async def chatCompletion(self, model: str, messages: List[Dict], tools: Optional[List[Dict]] = None) -> ChatResponse:
        kwargs = {
            "model": model,
            "messages": messages
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        for attempt in range(self.maxRetries):
            try:
                logger.debug(f"OpenAIClient SDK request: model={model}, messages={len(messages)} (Attempt {attempt + 1})")
                completion = await self._client.chat.completions.create(**kwargs)
                return self._mapCompletion(completion)

            except Exception as exc:
                logger.error(f"OpenAI SDK error (Attempt {attempt + 1}): {exc}")
                if attempt == self.maxRetries - 1:
                    raise
                await anyio.sleep(2 ** attempt)

        raise RuntimeError("OpenAIClient failed after maximum retries")

    def _mapCompletion(self, completion) -> ChatResponse:
        """Internal mapper from OpenAI SDK objects to ChatResponse."""
        choice = completion.choices[0]
        msg = choice.message
        content = msg.content or ""
        
        # OpenRouter / SDK extract reasoning if it's in model_extra or reasoning_content
        reasoning = None
        if hasattr(msg, 'reasoning_content') and msg.reasoning_content:
            reasoning = msg.reasoning_content
        elif hasattr(msg, 'model_extra') and msg.model_extra:
            reasoning = msg.model_extra.get('reasoning')
            
        # Fallback: check content for common thinking tags (DeepSeek style)
        if not reasoning and "<think>" in content and "</think>" in content:
            match = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
            if match:
                reasoning = match.group(1).strip()
                content = content.replace(match.group(0), "").strip()

        # Map tool calls
        toolCallsMapping = None
        if msg.tool_calls:
            toolCallsMapping = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                } for tc in msg.tool_calls
            ]

        usageMap = {
            "prompt_tokens": completion.usage.prompt_tokens if completion.usage else 0,
            "completion_tokens": completion.usage.completion_tokens if completion.usage else 0,
            "total_tokens": completion.usage.total_tokens if completion.usage else 0,
        }

        return ChatResponse(
            id=completion.id,
            content=content,
            role=msg.role,
            reasoning=reasoning,
            toolCalls=toolCallsMapping,
            usage=_normalizeUsage(usageMap),
            finishReason=choice.finish_reason
        )

def _normalizeUsage(usage: Any) -> Dict[str, int]:
    """Normalize any usage object/dict into a consistent {prompt_tokens, completion_tokens, total_tokens} dict."""
    if isinstance(usage, dict):
        raw = usage
    elif hasattr(usage, "__dict__"):
        raw = usage.__dict__
    else:
        raw = {}
    prompt = int(raw.get("prompt_tokens", 0) or 0)
    completion = int(raw.get("completion_tokens", 0) or 0)
    total = int(raw.get("total_tokens", 0) or prompt + completion)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total
    }

def getLlmClient(
    provider: str,
    model: str,
    apiKey: Optional[str] = None,
    baseUrl: Optional[str] = None,
    backoffCap: int = 60
) -> ILlmClient:
    """
    Factory to instantiate the correct LLM client based on provider.
    Handles URL normalization so callers never need to know which URL format each client expects:
      - openai:     SDK auto-appends /chat/completions, so we strip it if caller passed the full endpoint.
      - openrouter: Raw httpx, so we ensure the full endpoint URL is present.
      - local:      Uses base URL only (we append /v1/chat/completions ourselves).
    """
    provider = provider.lower()

    if provider == "local":
        return LocalLlmClient(
            baseUrl=baseUrl or "http://localhost:11434",
            model=model
        )

    elif provider == "openai":
        # SDK appends /chat/completions itself — strip it if the caller passed the full endpoint
        sdkBase = re.sub(r"/chat/completions$", "", baseUrl or OpenAIClient.OPENROUTER_BASE_URL).rstrip("/")
        return OpenAIClient(
            apiKey=apiKey or "",
            baseUrl=sdkBase,
            backoffCap=backoffCap
        )

    else:  # openrouter — raw httpx needs the full endpoint
        openRouterDefault = "https://openrouter.ai/api/v1/chat/completions"
        rawEndpoint = baseUrl or openRouterDefault
        if not rawEndpoint.rstrip("/").endswith("/chat/completions"):
            rawEndpoint = rawEndpoint.rstrip("/") + "/chat/completions"
        return OpenRouterClient(
            apiKey=apiKey or "",
            baseUrl=rawEndpoint,
            backoffCap=backoffCap
        )
