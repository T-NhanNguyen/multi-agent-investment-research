# OpenAI Compatibility & Local Inference

This guide explains why and how we use the OpenAI SDK to talk to local models.

## What is "OpenAI-Compatibility"?

Most modern, high-performance local inference engines (the software that actually runs the AI model on your computer) are designed to be **"OpenAI-Compatible."**

This means they implement the exact same communication standards (API endpoints and JSON formats) that the official OpenAI servers use. When a local tool is OpenAI-compatible, it means it has a `/v1/chat/completions` endpoint that accepts the same messages that ChatGPT does.

### Common Compatible Engines:

- **vLLM**: High-speed serving for data centers.
- **Ollama**: The most popular "one-click" runner for Mac, Linux, and Windows.
- **Llama.cpp**: Optimized for consumer CPUs and Apple Silicon.
- **LM Studio**: A GUI for downloading and testing models locally.

---

## Why Use the Official SDK for Local Models?

In our system, we use the `OpenAIClient` (which wraps the official `openai` Python SDK) to talk to these local runners. This provides several "Pro" benefits:

1.  **Robust Networking**: The official SDK handles complex things like connection pooling, keep-alive, and efficient streaming better than simple custom code.
2.  **Developer Convenience**: We get "IntelliSense" (code completion) and strict type-checking, making the code harder to break.
3.  **No Code Changes**: We can swap between a $100,000 GPU cluster (OpenAI) and a $500 home laptop (Ollama) just by changing a single `base_url` string.

## How it works in this project

When you set `LLM_PROVIDER="openai"` and a `LOCAL_LLM_URL` in your `.env`, the system tells the OpenAI SDK: _"Don't go to api.openai.com. Instead, send everything to my local machine at this address."_

The SDK doesn't know (or care) that it's talking to your laptop instead of a multi-billion dollar data center—it just sees a compatible API and goes to work.
