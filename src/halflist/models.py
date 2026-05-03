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


class ToolBenchmark(BaseModel):
    tool_name: str
    iterations: int
    min_ms: float
    max_ms: float
    mean_ms: float
    median_ms: float
    p95_ms: float
    p99_ms: float
    errors: int = 0
    skipped: bool = False
    skip_reason: str | None = None
    latencies: list[float] = []


class BenchReport(BaseModel):
    version: str
    timestamp: str
    server_info: ServerInfo | None = None
    transport: str
    connection_ms: float
    discovery_ms: float
    tool_count: int
    benchmarked_count: int
    iterations: int
    warmup: int
    benchmarks: list[ToolBenchmark]
    total_calls: int
    total_duration_ms: float


class AuditReport(BaseModel):
    version: str
    timestamp: str
    server_info: ServerInfo | None = None
    transport: str
    score: int
    suites: list[SuiteResult]
    total_passed: int
    total_failed: int
    total_warned: int
    connection_ms: float
    discovery_ms: float
    tool_count: int
    benchmarked_count: int
    iterations: int
    warmup: int
    benchmarks: list[ToolBenchmark]
    total_calls: int
    total_duration_ms: float


class PinData(BaseModel):
    server_name: str
    server_version: str
    timestamp: str
    tool_hashes: dict[str, str]


class WatchProbe(BaseModel):
    timestamp: str
    status: Literal["ok", "degraded", "down"]
    server_info: ServerInfo | None = None
    connection_ms: float | None = None
    handshake_passed: int = 0
    handshake_failed: int = 0
    handshake_warned: int = 0
    tool_count: int | None = None
    error: str | None = None
    probe_duration_ms: float
