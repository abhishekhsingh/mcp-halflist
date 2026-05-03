import sys
from pathlib import Path

import pytest

from halflist.client import HalflistClient
from halflist.suites.prompts import PromptsSuite

SERVERS_DIR = Path(__file__).parent.parent / "servers"


def _full_cmd() -> str:
    return f"{sys.executable} {SERVERS_DIR / 'full_server.py'}"


def _good_cmd() -> str:
    return f"{sys.executable} {SERVERS_DIR / 'good_server.py'}"


@pytest.mark.asyncio
async def test_prompts_suite_full_server() -> None:
    client = HalflistClient(timeout=30, quiet=True)
    try:
        await client.connect_stdio(_full_cmd())
        await client.initialize()

        suite = PromptsSuite(client)
        result = await suite.run()

        assert result.name == "prompts"
        assert result.failed == 0
        assert result.passed > 0

        check_names = [c.name for c in result.checks]
        assert "prompts/list returns valid array" in check_names
        assert "At least 1 prompt exists" in check_names
        assert "Every prompt has name" in check_names
        assert "prompts/get returns valid messages" in check_names
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_prompts_suite_no_prompts() -> None:
    client = HalflistClient(timeout=30, quiet=True)
    try:
        await client.connect_stdio(_good_cmd())
        await client.initialize()

        suite = PromptsSuite(client)
        result = await suite.run()

        assert result.name == "prompts"
        assert result.failed == 0
        statuses = [c.status for c in result.checks]
        assert "WARN" in statuses or "SKIP" in statuses
    finally:
        await client.close()
