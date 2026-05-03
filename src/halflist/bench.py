from __future__ import annotations

import statistics
import time
from typing import Callable

from mcp import types

from halflist.client import HalflistClient
from halflist.models import ToolBenchmark
from halflist.schema_gen import generate_args


async def bench_tool(
    client: HalflistClient,
    tool: types.Tool,
    iterations: int,
    warmup: int,
    on_call: Callable[[int], None] | None = None,
) -> ToolBenchmark:
    args = generate_args(tool.inputSchema)
    errors = 0

    warmup_failures = 0
    for _ in range(warmup):
        try:
            result = await client.call_tool(tool.name, args)
            if getattr(result, "isError", False):
                warmup_failures += 1
        except Exception:
            warmup_failures += 1

    if warmup > 0 and warmup_failures == warmup:
        return ToolBenchmark(
            tool_name=tool.name,
            iterations=0,
            min_ms=0, max_ms=0, mean_ms=0, median_ms=0,
            p95_ms=0, p99_ms=0, errors=0,
            skipped=True,
            skip_reason="all warmup calls failed",
        )

    latencies: list[float] = []
    for i in range(iterations):
        start = time.monotonic()
        try:
            result = await client.call_tool(tool.name, args)
            elapsed = (time.monotonic() - start) * 1000
            if getattr(result, "isError", False):
                errors += 1
            latencies.append(elapsed)
        except Exception:
            elapsed = (time.monotonic() - start) * 1000
            errors += 1
            latencies.append(elapsed)
        if on_call:
            on_call(i + 1)

    if not latencies:
        return ToolBenchmark(
            tool_name=tool.name,
            iterations=iterations,
            min_ms=0, max_ms=0, mean_ms=0, median_ms=0,
            p95_ms=0, p99_ms=0, errors=errors,
        )

    raw_latencies = [round(v, 2) for v in latencies]
    latencies.sort()
    quantiles = statistics.quantiles(latencies, n=100) if len(latencies) >= 2 else latencies
    p95_idx = min(94, len(quantiles) - 1) if quantiles else 0
    p99_idx = min(98, len(quantiles) - 1) if quantiles else 0

    max_val = latencies[-1]
    p95_raw = quantiles[p95_idx] if quantiles else max_val
    p99_raw = quantiles[p99_idx] if quantiles else max_val

    return ToolBenchmark(
        tool_name=tool.name,
        iterations=iterations,
        min_ms=round(latencies[0], 2),
        max_ms=round(max_val, 2),
        mean_ms=round(statistics.mean(latencies), 2),
        median_ms=round(statistics.median(latencies), 2),
        p95_ms=round(min(p95_raw, max_val), 2),
        p99_ms=round(min(p99_raw, max_val), 2),
        errors=errors,
        latencies=raw_latencies,
    )


def select_tools(
    all_tools: list[types.Tool],
    tool_names: list[str] | None,
    bench_all: bool,
    default_limit: int = 5,
) -> list[types.Tool]:
    if tool_names:
        name_set = set(tool_names)
        selected = [t for t in all_tools if t.name in name_set]
        return selected
    if bench_all:
        return list(all_tools)
    return list(all_tools[:default_limit])
