from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ServerInfo(BaseModel):
    name: str
    version: str


class CheckResult(BaseModel):
    name: str
    status: Literal["PASS", "FAIL", "WARN", "SKIP"]
    message: str | None = None
    duration_ms: float = 0.0
    suite: str


class SuiteResult(BaseModel):
    name: str
    checks: list[CheckResult]
    passed: int
    failed: int
    warned: int
    skipped: int
    duration_ms: float


class HalflistReport(BaseModel):
    version: str
    timestamp: str
    server_info: ServerInfo | None = None
    transport: str
    suites: list[SuiteResult]
    score: int
    total_passed: int
    total_failed: int
    total_warned: int
    total_duration_ms: float
