"""AI orchestration: consent + budget checks, circuit breaker, schema validation with one bounded
repair attempt, output filtering, usage logging and graceful degradation to deterministic logic.

LLM output can *propose* content only. No function here performs side effects other than
writing an AIUsageLog row; callers decide what to persist.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import SYSTEM_PREAMBLE, load_prompt
from app.ai.providers import get_provider, parse_json_object
from app.config import get_settings
from app.logging_setup import request_id_var
from app.models import AIUsageLog, ConsentRecord, UserSettings

log = logging.getLogger("jobpilot.ai")

COST_PER_1K = {"openai": (0.00015, 0.0006), "gemini": (0.000075, 0.0003), "mock": (0.0, 0.0)}

_SECRET_PATTERNS = [
    re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{10,}"),
    re.compile(r"(?i)\bapi[_ -]?key\b"),
    re.compile(r"(?i)system prompt"),
    re.compile(r"(?i)BEGIN (?:RSA |EC )?PRIVATE KEY"),
]
_URL_RE = re.compile(r"https?://[^\s\"'<>)]+")


class OutputRejected(Exception):
    pass


def filter_output(text: str, allowed_urls: Iterable[str] = ()) -> None:
    """Reject model output that references secrets/system prompts or unexpected URLs."""
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            raise OutputRejected("output references secrets or system prompt")
    allowed = {u.rstrip("/") for u in allowed_urls}
    for url in _URL_RE.findall(text):
        if url.rstrip("/.,") not in allowed:
            raise OutputRejected(f"output contains unexpected URL: {url[:60]}")


class _Breaker:
    def __init__(self, threshold: int = 5, cooldown: float = 60.0):
        self.threshold, self.cooldown = threshold, cooldown
        self.failures = 0
        self.opened_at: float | None = None

    def allow(self) -> bool:
        if self.opened_at is None:
            return True
        if time.monotonic() - self.opened_at > self.cooldown:
            self.opened_at, self.failures = None, 0
            return True
        return False

    def record(self, ok: bool) -> None:
        if ok:
            self.failures = 0
            return
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = time.monotonic()


breaker = _Breaker()


@dataclass
class AIResult[T: BaseModel]:
    value: T
    generator: str  # e.g. "openai:gpt-4o-mini" or "deterministic"
    prompt_version: str | None
    degraded_reason: str | None = None


async def ai_consented(session: AsyncSession, user_id: uuid.UUID) -> bool:
    row = (
        await session.execute(
            select(ConsentRecord)
            .where(ConsentRecord.user_id == user_id, ConsentRecord.purpose == "ai_processing")
            .order_by(ConsentRecord.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return bool(row and row.granted)


async def tokens_used_today(session: AsyncSession, user_id: uuid.UUID | None) -> int:
    since = datetime.now(UTC) - timedelta(days=1)
    q = select(func.coalesce(func.sum(AIUsageLog.tokens_in + AIUsageLog.tokens_out), 0)).where(
        AIUsageLog.created_at >= since
    )
    if user_id is not None:
        q = q.where(AIUsageLog.user_id == user_id)
    return int((await session.execute(q)).scalar_one())


async def user_budget(session: AsyncSession, user_id: uuid.UUID) -> int:
    s = (await session.execute(select(UserSettings).where(UserSettings.user_id == user_id))).scalar_one_or_none()
    default = get_settings().ai_daily_token_budget_per_user
    return min(s.ai_daily_token_budget, default) if s and s.ai_daily_token_budget else default


async def budget_status(session: AsyncSession, user_id: uuid.UUID) -> dict[str, int]:
    return {"used_last_24h": await tokens_used_today(session, user_id), "budget": await user_budget(session, user_id)}


def _log_usage(
    session: AsyncSession,
    user_id: uuid.UUID,
    provider: str,
    model: str,
    task: str,
    version: str,
    tin: int,
    tout: int,
    started: float,
    outcome: str,
) -> None:
    rate_in, rate_out = COST_PER_1K.get(provider, (0.0, 0.0))
    session.add(
        AIUsageLog(
            user_id=user_id,
            provider=provider,
            model=model,
            task=task,
            prompt_version=version,
            tokens_in=tin,
            tokens_out=tout,
            latency_ms=int((time.monotonic() - started) * 1000),
            cost_estimate_usd=round(tin / 1000 * rate_in + tout / 1000 * rate_out, 6),
            outcome=outcome,
            correlation_id=request_id_var.get() or "",
        )
    )


async def generate_structured[T: BaseModel](
    session: AsyncSession,
    user_id: uuid.UUID,
    task: str,
    schema: type[T],
    variables: dict[str, str],
    fallback: Callable[[], T],
    allowed_urls: Iterable[str] = (),
    validate: Callable[[T], None] | None = None,
) -> AIResult[T]:
    """Run `task` through the configured provider, or fall back to the deterministic `fallback`."""
    provider = get_provider()
    template = load_prompt(task)
    started = time.monotonic()

    def degrade(reason: str) -> AIResult[T]:
        return AIResult(fallback(), "deterministic", template.version, degraded_reason=reason)

    if provider.name == "mock":
        _log_usage(session, user_id, "mock", "mock-deterministic", task, template.version, 0, 0, started, "ok")
        return AIResult(fallback(), "deterministic", template.version)
    if not await ai_consented(session, user_id):
        return degrade("ai_consent_not_granted")
    if await tokens_used_today(session, user_id) >= await user_budget(session, user_id):
        return degrade("user_token_budget_exhausted")
    if await tokens_used_today(session, None) >= get_settings().ai_daily_token_budget_global:
        return degrade("global_token_budget_exhausted")
    if not breaker.allow():
        return degrade("provider_circuit_open")

    prompt = template.render(**variables)
    json_schema = schema.model_json_schema()
    last_error = ""
    for attempt in range(2):  # initial + one bounded repair attempt
        attempt_prompt = (
            prompt
            if attempt == 0
            else (f"{prompt}\n\nYour previous answer was invalid: {last_error[:300]}. Return corrected JSON only.")
        )
        try:
            raw = await provider.complete_json(SYSTEM_PREAMBLE, attempt_prompt, json_schema)
        except Exception as exc:  # network / HTTP errors are not retried beyond the breaker
            breaker.record(False)
            _log_usage(session, user_id, provider.name, "?", task, template.version, 0, 0, started, "error")
            log.warning("ai provider error task=%s err=%s", task, type(exc).__name__)
            return degrade("provider_error")
        try:
            filter_output(raw.text, allowed_urls)
            value = schema.model_validate(parse_json_object(raw.text))
            if validate:
                validate(value)
        except OutputRejected as exc:
            _log_usage(
                session,
                user_id,
                provider.name,
                raw.model,
                task,
                template.version,
                raw.tokens_in,
                raw.tokens_out,
                started,
                "rejected_by_filter",
            )
            breaker.record(True)
            return degrade(f"output_rejected: {exc}")
        except (ValidationError, ValueError) as exc:
            last_error = str(exc)
            _log_usage(
                session,
                user_id,
                provider.name,
                raw.model,
                task,
                template.version,
                raw.tokens_in,
                raw.tokens_out,
                started,
                "invalid_schema",
            )
            continue
        breaker.record(True)
        _log_usage(
            session,
            user_id,
            provider.name,
            raw.model,
            task,
            template.version,
            raw.tokens_in,
            raw.tokens_out,
            started,
            "ok",
        )
        return AIResult(value, f"{provider.name}:{raw.model}", template.version)
    return degrade("schema_validation_failed")


async def embed_texts(texts: list[str], allow_remote: bool) -> tuple[str, list[list[float]]]:
    """Embeddings degrade to the deterministic hashing embedder on any provider failure.

    `allow_remote` must be False unless the user consented to AI processing.
    """
    from app.ai.providers import hashing_embed

    provider = get_provider()
    if allow_remote and provider.name != "mock" and breaker.allow():
        try:
            return await provider.embed(texts)
        except Exception:
            breaker.record(False)
    return "mock-hash-256", [hashing_embed(t) for t in texts]
