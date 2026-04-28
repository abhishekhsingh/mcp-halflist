from __future__ import annotations

import time
from datetime import datetime, timezone

from halflist.client import HalflistClient
from halflist.models import WatchProbe
from halflist.suites.handshake import HandshakeSuite


async def run_probe(command: str, quiet: bool, timeout: int) -> WatchProbe:
    start = time.monotonic()
    client = HalflistClient(timeout=timeout, quiet=quiet)

    try:
        t0 = time.monotonic()
        await client.connect_stdio(command)
        server_info = await client.initialize()
        connection_ms = (time.monotonic() - t0) * 1000
    except Exception as e:
        probe_duration = (time.monotonic() - start) * 1000
        await client.close()
        return WatchProbe(
            timestamp=datetime.now(timezone.utc).isoformat(),
            status="down",
            error=str(e),
            probe_duration_ms=round(probe_duration, 2),
        )

    try:
        suite = HandshakeSuite(client)
        suite_result = await suite.run()

        try:
            tools = await client.list_tools()
            tool_count = len(tools)
        except Exception:
            tool_count = None

        probe_duration = (time.monotonic() - start) * 1000

        if suite_result.failed > 0:
            status = "degraded"
        else:
            status = "ok"

        return WatchProbe(
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=status,
            server_info=server_info,
            connection_ms=round(connection_ms, 2),
            handshake_passed=suite_result.passed,
            handshake_failed=suite_result.failed,
            handshake_warned=suite_result.warned,
            tool_count=tool_count,
            probe_duration_ms=round(probe_duration, 2),
        )
    finally:
        await client.close()
