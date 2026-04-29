from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from halflist.client import HalflistClient
from halflist.suites.security import SecuritySuite


@pytest.fixture
async def poisoned_client(poisoned_server_cmd: str):
    client = HalflistClient(timeout=30, quiet=True)
    await client.connect_stdio(poisoned_server_cmd)
    await client.initialize()
    yield client
    await client.close()


@pytest.fixture
async def good_client(good_server_cmd: str):
    client = HalflistClient(timeout=30, quiet=True)
    await client.connect_stdio(good_server_cmd)
    await client.initialize()
    yield client
    await client.close()


async def test_security_detects_poisoned_server(poisoned_client: HalflistClient) -> None:
    suite = SecuritySuite(poisoned_client)
    result = await suite.run()

    check_map = {c.name: c for c in result.checks}
    assert check_map["Prompt injection scan"].status == "FAIL"
    assert check_map["Data exfiltration references"].status == "FAIL"
    assert check_map["Cross-tool manipulation"].status == "FAIL"
    assert check_map["Suspicious encoding"].status == "FAIL"
    assert check_map["Tool pin verification"].status == "SKIP"


async def test_security_passes_good_server(good_client: HalflistClient) -> None:
    suite = SecuritySuite(good_client)
    result = await suite.run()

    check_map = {c.name: c for c in result.checks}
    assert check_map["Prompt injection scan"].status == "PASS"
    assert check_map["Data exfiltration references"].status == "PASS"
    assert check_map["Cross-tool manipulation"].status == "PASS"
    assert check_map["Suspicious encoding"].status == "PASS"


async def test_pin_verification_no_pin_file(poisoned_client: HalflistClient) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        suite = SecuritySuite(
            poisoned_client, verify_pins=True, pins_dir=Path(tmpdir)
        )
        result = await suite.run()

        check_map = {c.name: c for c in result.checks}
        assert check_map["Tool pin verification"].status == "WARN"
        assert "No pins found" in (check_map["Tool pin verification"].message or "")


async def test_pin_verification_matching(good_client: HalflistClient) -> None:
    import hashlib

    tools = await good_client.list_tools()

    tool_hashes: dict[str, str] = {}
    for t in tools:
        payload = json.dumps(
            {"name": t.name, "description": t.description, "inputSchema": t.inputSchema},
            sort_keys=True,
        )
        tool_hashes[t.name] = hashlib.sha256(payload.encode()).hexdigest()

    with tempfile.TemporaryDirectory() as tmpdir:
        pin_file = Path(tmpdir) / "good-test-server.json"
        pin_file.write_text(json.dumps({"tool_hashes": tool_hashes}))

        suite = SecuritySuite(
            good_client, verify_pins=True, pins_dir=Path(tmpdir)
        )
        result = await suite.run()

        check_map = {c.name: c for c in result.checks}
        assert check_map["Tool pin verification"].status == "PASS"


async def test_pin_verification_changed(good_client: HalflistClient) -> None:
    tools = await good_client.list_tools()
    fake_hashes = {t.name: "0000000000000000" for t in tools}

    with tempfile.TemporaryDirectory() as tmpdir:
        pin_file = Path(tmpdir) / "good-test-server.json"
        pin_file.write_text(json.dumps({"tool_hashes": fake_hashes}))

        suite = SecuritySuite(
            good_client, verify_pins=True, pins_dir=Path(tmpdir)
        )
        result = await suite.run()

        check_map = {c.name: c for c in result.checks}
        assert check_map["Tool pin verification"].status == "FAIL"
        assert "Hash changed" in (check_map["Tool pin verification"].message or "")


async def test_security_suite_has_five_checks(poisoned_client: HalflistClient) -> None:
    suite = SecuritySuite(poisoned_client)
    result = await suite.run()
    assert len(result.checks) == 5


async def test_security_prompt_injection_details(poisoned_client: HalflistClient) -> None:
    suite = SecuritySuite(poisoned_client)
    result = await suite.run()

    check_map = {c.name: c for c in result.checks}
    msg = check_map["Prompt injection scan"].message or ""
    assert "sneaky_exfil" in msg
    assert "<IMPORTANT> tags" in msg
