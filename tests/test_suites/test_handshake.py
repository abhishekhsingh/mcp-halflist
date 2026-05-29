import pytest

from halflist.client import HalflistClient
from halflist.suites.handshake import HandshakeSuite


@pytest.mark.asyncio
async def test_handshake_good_server(good_server_cmd: str) -> None:
    client = HalflistClient()
    try:
        await client.connect_stdio(good_server_cmd)
        await client.initialize()

        suite = HandshakeSuite(client)
        result = await suite.run()

        assert result.name == "handshake"
        assert len(result.checks) == 6

        for check in result.checks:
            assert check.status in ("PASS", "WARN"), (
                f"{check.name}: {check.status} - {check.message}"
            )

        assert result.passed >= 5
    finally:
        await client.close()
