"""Logging setup with secret redaction."""

from __future__ import annotations

import logging
import os
import re

_SECRET_ENV_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD")


def _secret_values() -> list[str]:
    values = []
    for name, value in os.environ.items():
        if any(h in name.upper() for h in _SECRET_ENV_HINTS) and value and len(value) >= 8:
            values.append(value)
    return values


def redact(text: str) -> str:
    """Remove any known secret values and common key shapes from a string."""
    for value in _secret_values():
        text = text.replace(value, "***REDACTED***")
    return re.sub(r"(sk-|AIza)[A-Za-z0-9_\-]{16,}", r"\1***REDACTED***", text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        if isinstance(record.args, tuple):
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        return True


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if any(getattr(h, "_codeforge", False) for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler._codeforge = True  # type: ignore[attr-defined]
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter())
    root.addHandler(handler)
    root.setLevel(level)
    for noisy in ("LiteLLM", "litellm", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
