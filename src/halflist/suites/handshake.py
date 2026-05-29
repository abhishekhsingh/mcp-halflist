from __future__ import annotations

from halflist.models import SuiteResult
from halflist.suites.base import CheckSuite


class HandshakeSuite(CheckSuite):
    name = "handshake"

    async def run(self) -> SuiteResult:
        start = self.measure()

        result = self.client.init_result
        if result is None:
            self.record("Server responds to initialize", "FAIL", "No init result stored")
            return self.build_result((self.measure() - start) * 1000)

        self.record("Server responds to initialize", "PASS")

        if hasattr(result, "protocolVersion") and result.protocolVersion:
            self.record("Protocol version returned", "PASS", f"v{result.protocolVersion}")
        else:
            self.record("Protocol version returned", "FAIL", "Missing protocolVersion")

        if hasattr(result, "capabilities") and result.capabilities is not None:
            self.record("Capabilities object present", "PASS")
        else:
            self.record("Capabilities object present", "FAIL", "Missing capabilities")

        if (
            hasattr(result, "serverInfo")
            and result.serverInfo
            and hasattr(result.serverInfo, "name")
            and result.serverInfo.name
            and hasattr(result.serverInfo, "version")
            and result.serverInfo.version
        ):
            self.record(
                "Server info has name and version",
                "PASS",
                f"{result.serverInfo.name} v{result.serverInfo.version}",
            )
        else:
            self.record(
                "Server info has name and version", "FAIL", "Missing or incomplete serverInfo"
            )

        try:
            from mcp.types import InitializedNotification

            await self.client.session.send_notification(InitializedNotification())
            self.record("Initialized notification accepted", "PASS")
        except Exception as e:
            self.record("Initialized notification accepted", "WARN", str(e))

        t0 = self.measure()
        pong = await self.client.ping()
        dur = (self.measure() - t0) * 1000
        if pong:
            self.record("Ping returns pong", "PASS", f"{dur:.0f}ms")
        else:
            self.record("Ping returns pong", "FAIL", "Ping failed")

        return self.build_result((self.measure() - start) * 1000)
