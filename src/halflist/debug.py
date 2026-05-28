from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

import httpx

logger = logging.getLogger("halflist")

SENSITIVE_HEADERS = {"authorization", "cookie", "x-api-key", "x-auth-token"}

_MAX_ARGS_DISPLAY = 200


def setup_debug_logging(
    debug: bool = False,
    debug_log: str | None = None,
) -> None:
    if debug_log:
        debug = True

    env_level = os.environ.get("HALFLIST_LOG_LEVEL", "").upper()
    if env_level in ("DEBUG", "INFO", "WARNING", "ERROR"):
        level = getattr(logging, env_level)
    elif debug:
        level = logging.DEBUG
    else:
        return

    if debug:
        level = min(level, logging.DEBUG)

    stderr_fmt = logging.Formatter("DEBUG %(asctime)s %(message)s", datefmt="%H:%M:%S")
    stderr_fmt.default_msec_format = "%s.%03d"
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(stderr_fmt)

    logger.setLevel(level)
    logger.addHandler(stderr_handler)

    if debug_log:
        file_fmt = logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        file_fmt.default_msec_format = "%s.%03d"
        file_handler = logging.FileHandler(debug_log)
        file_handler.setFormatter(file_fmt)
        logger.addHandler(file_handler)

    sdk_level = logging.DEBUG if debug else logging.INFO
    for name in ("mcp", "httpx", "httpcore"):
        sdk_logger = logging.getLogger(name)
        sdk_logger.setLevel(sdk_level)
        sdk_logger.addHandler(stderr_handler)
        if debug_log:
            sdk_logger.addHandler(file_handler)


def _mask_headers(headers: httpx.Headers | dict[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    items = headers.items() if isinstance(headers, (httpx.Headers, dict)) else []
    for key, value in items:
        if key.lower() in SENSITIVE_HEADERS:
            result[key] = "*****"
        else:
            result[key] = value
    return result


def _truncate(text: str, max_len: int = _MAX_ARGS_DISPLAY) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


class MCPDebugLogger:
    def __init__(self, method: str, params: str = "") -> None:
        self.method = method
        self.params = _truncate(params) if params else ""
        self.start = 0.0

    def __enter__(self) -> MCPDebugLogger:
        self.start = time.perf_counter()
        msg = f"→ {self.method}"
        if self.params:
            msg += f" {self.params}"
        logger.debug(msg)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        if exc_type:
            elapsed = (time.perf_counter() - self.start) * 1000
            label = "TIMEOUT" if issubclass(exc_type, (TimeoutError,)) else f"ERROR {exc_type.__name__}"
            logger.debug(f"← {self.method}: {label} ({elapsed:.0f}ms)")
        return False

    def success(self, summary: str) -> None:
        elapsed = (time.perf_counter() - self.start) * 1000
        logger.debug(f"← {self.method}: {summary} ({elapsed:.0f}ms)")


def _format_args(args: dict[str, Any] | None) -> str:
    if not args:
        return ""
    try:
        return _truncate(json.dumps(args, default=str))
    except Exception:
        return _truncate(str(args))


async def _log_request(request: httpx.Request) -> None:
    masked = _mask_headers(request.headers)
    logger.debug(f"HTTP → {request.method} {request.url} [headers: {masked}]")


async def _log_response(response: httpx.Response) -> None:
    request = response.request
    size = len(response.content) if hasattr(response, "_content") else "?"
    logger.debug(
        f"HTTP ← {response.status_code} ({size}B) [{request.method} {request.url}]"
    )


def create_debug_event_hooks() -> dict[str, list]:
    if not logger.isEnabledFor(logging.DEBUG):
        return {}
    return {"request": [_log_request], "response": [_log_response]}
