import pytest

from halflist.client import HalflistClient
from halflist.suites.tools import ToolsSuite


@pytest.mark.asyncio
async def test_tools_good_server(good_server_cmd: str) -> None:
    client = HalflistClient()
    try:
        await client.connect_stdio(good_server_cmd)
        await client.initialize()

        suite = ToolsSuite(client)
        result = await suite.run()

        assert result.name == "tools"
        assert result.failed == 0

        statuses = [c.status for c in result.checks]
        assert "PASS" in statuses
        assert result.passed >= 8
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_tools_bad_server(bad_server_cmd: str) -> None:
    client = HalflistClient()
    try:
        await client.connect_stdio(bad_server_cmd)
        await client.initialize()

        suite = ToolsSuite(client)
        result = await suite.run()

        assert result.name == "tools"
        has_warn = any(c.status == "WARN" for c in result.checks)
        assert has_warn, "Expected at least one warning for bad server"

        desc_check = next(c for c in result.checks if "description" in c.name.lower())
        assert desc_check.status == "WARN"
        assert "empty description" in desc_check.message
    finally:
        await client.close()
