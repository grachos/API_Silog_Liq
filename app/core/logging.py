"""Structured logging setup with automatic secret and credential masking."""
import logging
import re
import sys
from contextvars import ContextVar
from typing import Optional
from app.core.config import settings

# Context variable for tracking request ID across async calls
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


class SecretMaskingFilter(logging.Filter):
    """
    Log filter that redacts sensitive values such as tokens, passwords,
    session cookies, and authorization headers from all log records.
    """
    PATTERNS = [
        # Bearer tokens
        (re.compile(r"(Bearer\s+)([A-Za-z0-9_\-\.]+)", re.IGNORECASE), r"\1***REDACTED_TOKEN***"),
        # Key-value passwords
        (re.compile(r"((?:password|passwd|clave|secret|token|api_key)[\"']?\s*[:=]\s*[\"']?)([^\"'\s,]+)", re.IGNORECASE), r"\1***REDACTED***"),
        # Silogtran/PHP Session Cookies
        (re.compile(r"(PHPSESSID=)([A-Za-z0-9]+)", re.IGNORECASE), r"\1***REDACTED_SESSION***"),
        # Authorization header in curl or text
        (re.compile(r"Authorization:\s*Bearer\s+[^\s]+", re.IGNORECASE), "Authorization: Bearer ***REDACTED***"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern, replacement in self.PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)

            # Explicit check for configured secrets if present
            if settings.SILOGTRAN_PASSWORD and settings.SILOGTRAN_PASSWORD in record.msg:
                record.msg = record.msg.replace(settings.SILOGTRAN_PASSWORD, "***REDACTED_PASSWORD***")
            if settings.API_TOKEN and settings.API_TOKEN in record.msg:
                record.msg = record.msg.replace(settings.API_TOKEN, "***REDACTED_API_TOKEN***")
            if settings.ADMIN_API_KEY and settings.ADMIN_API_KEY in record.msg:
                record.msg = record.msg.replace(settings.ADMIN_API_KEY, "***REDACTED_ADMIN_KEY***")

        # Inject request_id if available
        req_id = request_id_ctx.get()
        setattr(record, "request_id", req_id or "-")

        return True


class StructuredFormatter(logging.Formatter):
    """Clean structured log formatter."""
    def format(self, record: logging.LogRecord) -> str:
        req_id = getattr(record, "request_id", "-")
        record_msg = super().format(record)
        return f"[{self.formatTime(record, '%Y-%m-%d %H:%M:%S')}] [{record.levelname:<7}] [req_id={req_id}] {record.name}: {record_msg}"


def setup_logging() -> None:
    """Configures application logging with the masking filter and structured formatter."""
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL.upper())

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(settings.LOG_LEVEL.upper())
    handler.addFilter(SecretMaskingFilter())
    handler.setFormatter(StructuredFormatter())

    root_logger.addHandler(handler)

    # Set specific third-party library log levels to avoid noise
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
