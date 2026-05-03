import sys
from pathlib import Path

import pytest

from halflist.client import HalflistClient
from halflist.suites.resources import ResourcesSuite

SERVERS_DIR = Path(__file__).parent.parent / "servers"


def _full_cmd() -> str:
    return f"{sys.executable} {SERVERS_DIR / 'full_server.py'}"


def _good_cmd() -> str:
    return f"{sys.executable} {SERVERS_DIR / 'good_server.py'}"


@pytest.mark.asyncio
async def test_resources_suite_full_server() -> None:
    client = HalflistClient(timeout=30, quiet=True)
    try:
        await client.connect_stdio(_full_cmd())
        await client.initialize()

        suite = ResourcesSuite(client)
        result = await suite.run()

        assert result.name == "resources"
        assert result.failed == 0
        assert result.passed > 0

        check_names = [c.name for c in result.checks]
        assert "resources/list returns valid array" in check_names
        assert "At least 1 resource exists" in check_names
        assert "Every resource has uri" in check_names
        assert "resources/read returns valid content" in check_names
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_resources_suite_no_resources() -> None:
    client = HalflistClient(timeout=30, quiet=True)
    try:
        await client.connect_stdio(_good_cmd())
        await client.initialize()

        suite = ResourcesSuite(client)
        result = await suite.run()

        assert result.name == "resources"
        assert result.failed == 0
        statuses = [c.status for c in result.checks]
        assert "WARN" in statuses or "SKIP" in statuses
    finally:
        await client.close()
