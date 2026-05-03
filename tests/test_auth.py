from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from halflist.auth import fetch_oauth_token
from halflist.cli import app

runner = CliRunner()
SERVERS_DIR = Path(__file__).parent / "servers"


def _make_mock_client(response_json: dict, status_code: int = 200) -> MagicMock:
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = response_json

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False
    return mock_client


@pytest.mark.asyncio
async def test_fetch_oauth_token_success() -> None:
    mock_client = _make_mock_client({"access_token": "test-token-123", "token_type": "bearer"})

    with patch("halflist.auth.httpx.AsyncClient", return_value=mock_client):
        token = await fetch_oauth_token(
            token_url="https://auth.example.com/token",
            client_id="my-client",
            client_secret="my-secret",
            scope="read write",
        )

    assert token == "test-token-123"
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "https://auth.example.com/token"
    assert call_args[1]["data"]["grant_type"] == "client_credentials"
    assert call_args[1]["data"]["client_id"] == "my-client"
    assert call_args[1]["data"]["client_secret"] == "my-secret"
    assert call_args[1]["data"]["scope"] == "read write"


@pytest.mark.asyncio
async def test_fetch_oauth_token_no_scope() -> None:
    mock_client = _make_mock_client({"access_token": "tok"})

    with patch("halflist.auth.httpx.AsyncClient", return_value=mock_client):
        token = await fetch_oauth_token(
            token_url="https://auth.example.com/token",
            client_id="c",
            client_secret="s",
        )

    assert token == "tok"
    call_data = mock_client.post.call_args[1]["data"]
    assert "scope" not in call_data


@pytest.mark.asyncio
async def test_fetch_oauth_token_missing_access_token() -> None:
    mock_client = _make_mock_client({"token_type": "bearer"})

    with patch("halflist.auth.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ValueError, match="missing 'access_token'"):
            await fetch_oauth_token(
                token_url="https://auth.example.com/token",
                client_id="c",
                client_secret="s",
            )


# ── Real server tests (using local OAuth mock) ──────────────────────────────


@pytest.mark.asyncio
async def test_fetch_oauth_token_real_server(oauth_server: dict[str, str]) -> None:
    token = await fetch_oauth_token(
        token_url=oauth_server["url"],
        client_id=oauth_server["client_id"],
        client_secret=oauth_server["client_secret"],
    )
    assert token == f"mock-token-{oauth_server['client_id']}"


@pytest.mark.asyncio
async def test_fetch_oauth_token_real_server_with_scope(oauth_server: dict[str, str]) -> None:
    token = await fetch_oauth_token(
        token_url=oauth_server["url"],
        client_id=oauth_server["client_id"],
        client_secret=oauth_server["client_secret"],
        scope="read write",
    )
    assert token == f"mock-token-{oauth_server['client_id']}"


@pytest.mark.asyncio
async def test_fetch_oauth_token_real_server_bad_grant(oauth_server: dict[str, str]) -> None:
    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.post(oauth_server["url"], data={
            "grant_type": "authorization_code",
            "client_id": "c",
            "client_secret": "s",
        })
    assert resp.status_code == 400
    assert resp.json()["error"] == "unsupported_grant_type"


@pytest.mark.asyncio
async def test_fetch_oauth_token_real_server_missing_creds(oauth_server: dict[str, str]) -> None:
    import httpx

    with pytest.raises(httpx.HTTPStatusError):
        await fetch_oauth_token(
            token_url=oauth_server["url"],
            client_id="",
            client_secret="",
        )


def test_cli_check_full_server() -> None:
    cmd = f"{sys.executable} {SERVERS_DIR / 'full_server.py'}"
    result = runner.invoke(app, [
        "check", "--stdio", cmd,
        "--format", "json", "-q",
    ])
    assert result.exit_code == 0
    report = json.loads(result.output)
    assert report["total_failed"] == 0


# ── Mock-based unit tests (continued) ───────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_oauth_token_non_json_response() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.side_effect = Exception("Expecting value")

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False

    with patch("halflist.auth.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ValueError, match="non-JSON response"):
            await fetch_oauth_token(
                token_url="https://auth.example.com/token",
                client_id="c",
                client_secret="s",
            )


@pytest.mark.asyncio
async def test_fetch_oauth_token_empty_string_token() -> None:
    mock_client = _make_mock_client({"access_token": "", "token_type": "bearer"})

    with patch("halflist.auth.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ValueError, match="missing 'access_token'"):
            await fetch_oauth_token(
                token_url="https://auth.example.com/token",
                client_id="c",
                client_secret="s",
            )
