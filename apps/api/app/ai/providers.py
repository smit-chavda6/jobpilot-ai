"""Provider-agnostic LLM interface (spec §9) with Mock, OpenAI and Gemini implementations.

Only the Mock provider is exercised in tests/CI. OpenAI and Gemini implement the real HTTP
APIs but are *not live-verified* in this repository (no credentials available) - see STATUS.md.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.config import get_settings

EMBED_DIM_MOCK = 256


@dataclass
class RawCompletion:
    text: str
    tokens_in: int
    tokens_out: int
    model: str


class LLMProvider(Protocol):
    name: str

    async def complete_json(self, system: str, prompt: str, json_schema: dict[str, Any]) -> RawCompletion: ...

    async def embed(self, texts: list[str]) -> tuple[str, list[list[float]]]: ...


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


_TOKEN_RE = re.compile(r"[a-z0-9+#.]+")


def hashing_embed(text: str, dim: int = EMBED_DIM_MOCK) -> list[float]:
    """Deterministic bag-of-words hashing embedding (unigrams + bigrams), L2-normalised."""
    tokens = [t.strip(".") for t in _TOKEN_RE.findall(text.lower()) if len(t.strip(".")) > 1]
    vec = [0.0] * dim
    grams = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False)]
    for g in grams:
        h = int(hashlib.blake2b(g.encode(), digest_size=8).hexdigest(), 16)
        vec[h % dim] += 1.0 if (h >> 63) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class MockProvider:
    """Deterministic provider for development and tests.

    `complete_json` returns the empty object; the AI service then uses the deterministic
    fallback implementation for the task, which *is* the mock behaviour.
    """

    name = "mock"

    async def complete_json(self, system: str, prompt: str, json_schema: dict[str, Any]) -> RawCompletion:
        return RawCompletion("{}", estimate_tokens(system + prompt), 1, "mock-deterministic")

    async def embed(self, texts: list[str]) -> tuple[str, list[list[float]]]:
        return "mock-hash-256", [hashing_embed(t) for t in texts]


class OpenAIProvider:
    name = "openai"

    def __init__(self) -> None:
        s = get_settings()
        self.model = s.openai_model
        self.embed_model = s.openai_embedding_model
        self._client = httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={"Authorization": f"Bearer {s.openai_api_key}"},
            timeout=s.llm_timeout_seconds,
        )

    async def complete_json(self, system: str, prompt: str, json_schema: dict[str, Any]) -> RawCompletion:
        resp = await self._client.post(
            "/chat/completions",
            json={
                "model": self.model,
                "temperature": 0.2,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "output", "schema": json_schema, "strict": False},
                },
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})
        return RawCompletion(
            data["choices"][0]["message"]["content"],
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
            self.model,
        )

    async def embed(self, texts: list[str]) -> tuple[str, list[list[float]]]:
        resp = await self._client.post("/embeddings", json={"model": self.embed_model, "input": texts})
        resp.raise_for_status()
        return self.embed_model, [d["embedding"] for d in resp.json()["data"]]


class GeminiProvider:
    name = "gemini"

    def __init__(self) -> None:
        s = get_settings()
        self.model = s.gemini_model
        self._key = s.gemini_api_key
        self._client = httpx.AsyncClient(
            base_url="https://generativelanguage.googleapis.com/v1beta", timeout=s.llm_timeout_seconds
        )

    async def complete_json(self, system: str, prompt: str, json_schema: dict[str, Any]) -> RawCompletion:
        resp = await self._client.post(
            f"/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self._key},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usageMetadata", {})
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return RawCompletion(text, usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0), self.model)

    async def embed(self, texts: list[str]) -> tuple[str, list[list[float]]]:
        resp = await self._client.post(
            "/models/text-embedding-004:batchEmbedContents",
            headers={"x-goog-api-key": self._key},
            json={
                "requests": [{"model": "models/text-embedding-004", "content": {"parts": [{"text": t}]}} for t in texts]
            },
        )
        resp.raise_for_status()
        return "text-embedding-004", [e["values"] for e in resp.json()["embeddings"]]


_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        name = get_settings().llm_provider
        provider: LLMProvider
        if name == "openai":
            provider = OpenAIProvider()
        elif name == "gemini":
            provider = GeminiProvider()
        else:
            provider = MockProvider()
        _provider = provider
    return _provider


def set_provider(provider: LLMProvider | None) -> None:
    """Test hook for injecting fake providers."""
    global _provider
    _provider = provider


def parse_json_object(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    return json.loads(text)
