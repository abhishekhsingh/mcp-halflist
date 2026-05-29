import sys
from pathlib import Path

import pytest

from halflist.watch import run_probe

SERVERS_DIR = Path(__file__).parent / "servers"


def _good_cmd() -> str:
    return f"{sys.executable} {SERVERS_DIR / 'good_server.py'}"


@pytest.mark.asyncio
async def test_watch_single_probe_ok() -> None:
    probe = await run_probe(stdio=_good_cmd(), quiet=True, timeout=30)
    assert probe.status == "ok"
    assert probe.server_info is not None
    assert probe.connection_ms is not None
    assert probe.connection_ms > 0
    assert probe.tool_count == 5
    assert probe.handshake_passed > 0
    assert probe.handshake_failed == 0
    assert probe.error is None


@pytest.mark.asyncio
async def test_watch_two_probes() -> None:
    probes = []
    for _ in range(2):
        probe = await run_probe(stdio=_good_cmd(), quiet=True, timeout=30)
        probes.append(probe)

    assert len(probes) == 2
    for p in probes:
        assert p.status == "ok"
        assert p.probe_duration_ms > 0


@pytest.mark.asyncio
async def test_watch_bad_server_down() -> None:
    probe = await run_probe(
        stdio="nonexistent_binary_that_does_not_exist_xyz", quiet=True, timeout=5
    )
    assert probe.status == "down"
    assert probe.error is not None
    assert probe.probe_duration_ms > 0


@pytest.mark.asyncio
async def test_watch_no_transport_returns_down() -> None:
    probe = await run_probe(quiet=True, timeout=5)
    assert probe.status == "down"
    assert probe.error is not None
    assert "Provide either stdio or http_url" in probe.error
    assert probe.probe_duration_ms >= 0


@pytest.mark.asyncio
async def test_watch_http_bad_url_returns_down() -> None:
    probe = await run_probe(http_url="http://localhost:19999", quiet=True, timeout=5)
    assert probe.status == "down"
    assert probe.error is not None
    assert probe.probe_duration_ms > 0
