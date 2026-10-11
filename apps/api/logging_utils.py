"""Structured JSON logging with correlation IDs and PII redaction."""

import json
import logging
import re
from typing import Any, Dict

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
PHONE_REGEX = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
BEARER_REGEX = re.compile(r"Bearer\s+[A-Za-z0-9\-_\.]+", re.IGNORECASE)


def redact_pii(text: str) -> str:
    """Redacts emails, phone numbers, and bearer tokens from log messages."""
    if not isinstance(text, str):
        return text
    text = EMAIL_REGEX.sub("[EMAIL_REDACTED]", text)
    text = PHONE_REGEX.sub("[PHONE_REDACTED]", text)
    text = BEARER_REGEX.sub("Bearer [TOKEN_REDACTED]", text)
    return text


class JSONLogFormatter(logging.Formatter):
    """Formats log records as structured JSON with correlation/request ID and PII redaction."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_pii(record.getMessage()),
            "request_id": getattr(record, "request_id", None),
            "user_id": getattr(record, "user_id", None),
        }

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


def setup_logging(log_level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setFormatter(JSONLogFormatter())
    root.addHandler(handler)
