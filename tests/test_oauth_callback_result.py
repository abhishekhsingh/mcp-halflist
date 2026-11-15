"""The OAuth callback handlers hand the SDK an AuthorizationCodeResult that carries the RFC 9207 issuer."""

from __future__ import annotations

import asyncio
import io
import os
import sys

import httpx
import pytest
from mcp.shared.auth import AuthorizationCodeResult

from halflist.oauth_pkce import CallbackServer, _headless_callback, create_oauth_provider


async def _hit(port: int, query: str) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://127.0.0.1:{port}/callback?{query}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_callback_server_records_issuer() -> None:
    server = CallbackServer()
    try:
        server.start(asyncio.get_event_loop())
        await _hit(server.port, "code=c1&state=s1&iss=https%3A%2F%2Fauth.example")
        code, state = await asyncio.wait_for(server.wait_for_callback(), timeout=2)
        assert (code, state) == ("c1", "s1")
        assert server.iss == "https://auth.example"
    finally:
        server.stop()


@pytest.mark.asyncio
async def test_callback_server_issuer_is_none_when_absent() -> None:
    server = CallbackServer()
    try:
        server.start(asyncio.get_event_loop())
        await _hit(server.port, "code=c1&state=s1")
        await asyncio.wait_for(server.wait_for_callback(), timeout=2)
        assert server.iss is None
    finally:
        server.stop()


@pytest.mark.asyncio
async def test_browser_callback_handler_returns_authorization_code_result() -> None:
    provider, server, storage = create_oauth_provider("http://example.com/mcp")
    try:
        handler = provider.context.callback_handler
        task = asyncio.ensure_future(handler())
        await _hit(server.port, "code=c1&state=s1&iss=https%3A%2F%2Fauth.example")
        result = await asyncio.wait_for(task, timeout=2)
        assert isinstance(result, AuthorizationCodeResult)
        assert (result.code, result.state, result.iss) == ("c1", "s1", "https://auth.example")
    finally:
        server.stop()
        storage.clear()


@pytest.mark.asyncio
async def test_headless_callback_handler_via_callback_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Headless mode also reads stdin. Emulate an idle terminal: a pipe nothing writes to.
    read_fd, write_fd = os.pipe()
    monkeypatch.setattr(sys, "stdin", os.fdopen(read_fd))
    provider, server, storage = create_oauth_provider("http://example.com/mcp", no_browser=True)
    try:
        handler = provider.context.callback_handler
        task = asyncio.ensure_future(handler())
        await asyncio.sleep(0.2)
        await _hit(server.port, "code=c2&state=s2")
        result = await asyncio.wait_for(task, timeout=5)
        assert isinstance(result, AuthorizationCodeResult)
        assert (result.code, result.state, result.iss) == ("c2", "s2", None)
    finally:
        os.close(write_fd)  # lets the stdin reader thread finish
        server.stop()
        storage.clear()


@pytest.mark.asyncio
async def test_headless_paste_records_issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    server = CallbackServer()
    try:
        server.start(asyncio.get_event_loop())
        pasted = "http://127.0.0.1:3030/callback?code=c3&state=s3&iss=https%3A%2F%2Fauth.example\n"
        monkeypatch.setattr(sys, "stdin", io.StringIO(pasted))
        code, state = await asyncio.wait_for(_headless_callback(server), timeout=5)
        assert (code, state) == ("c3", "s3")
        assert server.iss == "https://auth.example"
    finally:
        server.stop()


@pytest.mark.asyncio
async def test_headless_paste_without_issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    server = CallbackServer()
    try:
        server.start(asyncio.get_event_loop())
        pasted = "http://127.0.0.1:3030/callback?code=c4&state=s4\n"
        monkeypatch.setattr(sys, "stdin", io.StringIO(pasted))
        code, state = await asyncio.wait_for(_headless_callback(server), timeout=5)
        assert (code, state) == ("c4", "s4")
        assert server.iss is None
    finally:
        server.stop()
