"""Abstract LLM Provider interface and implementations (Mock, Gemini, OpenAI)."""

import hashlib
from typing import Any, Dict, List, Optional, Protocol, Type, TypeVar

from pydantic import BaseModel

from apps.api.config import settings

T = TypeVar("T", bound=BaseModel)


class LLMProvider(Protocol):
    async def generate_structured(
        self,
        schema: Type[T],
        prompt: str,
        system_instruction: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> T: ...

    async def embed(self, texts: List[str]) -> List[List[float]]: ...


class MockProvider(LLMProvider):
    """Deterministic, zero-latency provider for development, tests, and CI."""

    async def generate_structured(
        self,
        schema: Type[T],
        prompt: str,
        system_instruction: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> T:
        # Generate deterministic mock values adhering to the Pydantic schema
        dummy_data: Dict[str, Any] = {}
        for name, field_info in schema.model_fields.items():
            field_type = field_info.annotation
            origin = getattr(field_type, "__origin__", None)

            if origin is list or field_type is list:
                dummy_data[name] = []
            elif origin is dict or field_type is dict:
                dummy_data[name] = {}
            elif field_type is int:
                dummy_data[name] = 100
            elif field_type is float:
                dummy_data[name] = 0.95
            elif field_type is bool:
                dummy_data[name] = True
            elif field_type is str:
                dummy_data[name] = f"Deterministic grounded response for {name}"
            else:
                dummy_data[name] = None

        return schema.model_validate(dummy_data)

    async def embed(self, texts: List[str]) -> List[List[float]]:
        embeddings = []
        for text in texts:
            # Deterministic 768-dim pseudorandom vector generated from text hash
            h = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [(b / 255.0) - 0.5 for b in h]
            # Tile to 768 dimensions
            vec_768 = (vec * (768 // len(vec) + 1))[:768]
            # Normalize vector
            norm = sum(x * x for x in vec_768) ** 0.5 or 1.0
            embeddings.append([x / norm for x in vec_768])
        return embeddings


class GeminiProvider(LLMProvider):
    """Google Gemini LLM provider implementation."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def generate_structured(
        self,
        schema: Type[T],
        prompt: str,
        system_instruction: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> T:
        # Fallback to Mock if key is absent or mock requested
        if not self.api_key:
            return await MockProvider().generate_structured(
                schema, prompt, system_instruction, correlation_id
            )
        # Production Gemini client invocation
        import httpx

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"},
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            return schema.model_validate_json(raw_text)

    async def embed(self, texts: List[str]) -> List[List[float]]:
        if not self.api_key:
            return await MockProvider().embed(texts)
        # Real Gemini embedContent endpoint call
        import httpx

        url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:batchEmbedContents?key={self.api_key}"
        requests = [
            {"model": "models/text-embedding-004", "content": {"parts": [{"text": t}]}}
            for t in texts
        ]
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json={"requests": requests})
            data = resp.json()
            return [e["values"] for e in data.get("embeddings", [])]


class OpenAIProvider(LLMProvider):
    """OpenAI API provider implementation."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def generate_structured(
        self,
        schema: Type[T],
        prompt: str,
        system_instruction: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> T:
        if not self.api_key:
            return await MockProvider().generate_structured(
                schema, prompt, system_instruction, correlation_id
            )
        import httpx

        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_instruction or "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions", headers=headers, json=payload
            )
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return schema.model_validate_json(content)

    async def embed(self, texts: List[str]) -> List[List[float]]:
        if not self.api_key:
            return await MockProvider().embed(texts)
        import httpx

        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"input": texts, "model": "text-embedding-3-small"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/embeddings", headers=headers, json=payload
            )
            data = resp.json()
            return [item["embedding"] for item in data.get("data", [])]


def get_llm_provider() -> LLMProvider:
    """Factory selecting provider based on configured environment settings."""
    if settings.LLM_PROVIDER == "gemini" and settings.GEMINI_API_KEY:
        return GeminiProvider(settings.GEMINI_API_KEY)
    elif settings.LLM_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        return OpenAIProvider(settings.OPENAI_API_KEY)
    return MockProvider()
