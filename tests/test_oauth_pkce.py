from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

from halflist.cli import app
from halflist.oauth_pkce import (
    CallbackServer,
    FileTokenStorage,
    _print_url_handler,
    create_oauth_provider,
    open_browser_handler,
)

runner = CliRunner()
SERVERS_DIR = Path(__file__).parent / "servers"


# ── CallbackServer tests ────────────────────────────────────────────────────


class TestCallbackServer:
    def test_start_binds_to_port(self) -> None:
        loop = asyncio.new_event_loop()
        server = CallbackServer(port=3035)
        try:
            server.start(loop)
            assert server.port == 3035
            assert server.redirect_uri == "http://127.0.0.1:3035/callback"
        finally:
            server.stop()
            loop.close()

    def test_start_finds_free_port_in_range(self) -> None:
        loop = asyncio.new_event_loop()
        server = CallbackServer()
        try:
            server.start(loop)
            assert 3030 <= server.port <= 3039
        finally:
            server.stop()
            loop.close()

    def test_start_port_fallback(self) -> None:
        loop = asyncio.new_event_loop()
        blocker = CallbackServer(port=3030)
        server = CallbackServer()
        try:
            blocker.start(loop)
            server.start(loop)
            assert server.port >= 3030
            assert server.port != blocker.port
        finally:
            server.stop()
            blocker.stop()
            loop.close()

    @pytest.mark.asyncio
    async def test_callback_receives_code_and_state(self) -> None:
        loop = asyncio.get_event_loop()
        server = CallbackServer()
        try:
            server.start(loop)
            url = f"http://127.0.0.1:{server.port}/callback?code=abc123&state=xyz789"

            async with httpx.AsyncClient() as client:
                resp = await client.get(url)
            assert resp.status_code == 200

            code, state = await asyncio.wait_for(server.wait_for_callback(), timeout=2)
            assert code == "abc123"
            assert state == "xyz789"
        finally:
            server.stop()

    @pytest.mark.asyncio
    async def test_callback_error_raises(self) -> None:
        loop = asyncio.get_event_loop()
        server = CallbackServer()
        try:
            server.start(loop)
            url = f"http://127.0.0.1:{server.port}/callback?error=access_denied"

            async with httpx.AsyncClient() as client:
                await client.get(url)

            with pytest.raises(RuntimeError, match="access_denied"):
                await asyncio.wait_for(server.wait_for_callback(), timeout=2)
        finally:
            server.stop()

    @pytest.mark.asyncio
    async def test_callback_404_on_wrong_path(self) -> None:
        loop = asyncio.get_event_loop()
        server = CallbackServer()
        try:
            server.start(loop)
            url = f"http://127.0.0.1:{server.port}/wrong"

            async with httpx.AsyncClient() as client:
                resp = await client.get(url)
            assert resp.status_code == 404
        finally:
            server.stop()

    def test_stop_idempotent(self) -> None:
        loop = asyncio.new_event_loop()
        server = CallbackServer()
        try:
            server.start(loop)
            server.stop()
            server.stop()
        finally:
            loop.close()


# ── FileTokenStorage tests ──────────────────────────────────────────────────


class TestFileTokenStorage:
    @pytest.fixture
    def storage(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FileTokenStorage:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        return FileTokenStorage("http://example.com/mcp")

    @pytest.mark.asyncio
    async def test_get_tokens_empty(self, storage: FileTokenStorage) -> None:
        assert await storage.get_tokens() is None

    @pytest.mark.asyncio
    async def test_set_and_get_tokens(self, storage: FileTokenStorage) -> None:
        from mcp.shared.auth import OAuthToken

        token = OAuthToken(access_token="test-access", token_type="Bearer", expires_in=3600)
        await storage.set_tokens(token)

        loaded = await storage.get_tokens()
        assert loaded is not None
        assert loaded.access_token == "test-access"
        assert loaded.expires_in == 3600

    @pytest.mark.asyncio
    async def test_get_client_info_empty(self, storage: FileTokenStorage) -> None:
        assert await storage.get_client_info() is None

    @pytest.mark.asyncio
    async def test_set_and_get_client_info(self, storage: FileTokenStorage) -> None:
        from mcp.shared.auth import OAuthClientInformationFull

        info = OAuthClientInformationFull(
            client_id="test-id",
            client_secret="test-secret",
            redirect_uris=["http://127.0.0.1:3030/callback"],
        )
        await storage.set_client_info(info)

        loaded = await storage.get_client_info()
        assert loaded is not None
        assert loaded.client_id == "test-id"
        assert loaded.client_secret == "test-secret"

    @pytest.mark.asyncio
    async def test_clear(self, storage: FileTokenStorage) -> None:
        from mcp.shared.auth import OAuthToken

        token = OAuthToken(access_token="tok", token_type="Bearer")
        await storage.set_tokens(token)
        assert await storage.get_tokens() is not None

        storage.clear()
        assert await storage.get_tokens() is None

    @pytest.mark.asyncio
    async def test_clear_nonexistent(self, storage: FileTokenStorage) -> None:
        storage.clear()

    @pytest.mark.asyncio
    async def test_file_permissions(self, storage: FileTokenStorage) -> None:
        from mcp.shared.auth import OAuthToken

        token = OAuthToken(access_token="tok", token_type="Bearer")
        await storage.set_tokens(token)

        assert storage._path.exists()
        mode = storage._path.stat().st_mode & 0o777
        assert mode == 0o600

        dir_mode = storage._dir.stat().st_mode & 0o777
        assert dir_mode == 0o700

    @pytest.mark.asyncio
    async def test_different_urls_different_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        s1 = FileTokenStorage("http://example.com/a")
        s2 = FileTokenStorage("http://example.com/b")
        assert s1._path != s2._path


# ── Handler tests ────────────────────────────────────────────────────────────


class TestHandlers:
    @pytest.mark.asyncio
    async def test_open_browser_handler(self) -> None:
        with patch("halflist.oauth_pkce.webbrowser.open") as mock_open:
            await open_browser_handler("https://example.com/auth")
            mock_open.assert_called_once_with("https://example.com/auth")

    @pytest.mark.asyncio
    async def test_print_url_handler(self, capsys: pytest.CaptureFixture[str]) -> None:
        await _print_url_handler("https://example.com/auth")


# ── create_oauth_provider tests ──────────────────────────────────────────────


class TestCreateOAuthProvider:
    def test_creates_provider_and_server(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            provider, server, storage = create_oauth_provider(
                "http://example.com/mcp"
            )
            assert server.port >= 3030
            assert provider is not None
            assert storage is not None
        finally:
            server.stop()
            storage.clear()
            loop.close()

    def test_custom_callback_port(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            provider, server, storage = create_oauth_provider(
                "http://example.com/mcp", callback_port=3037,
            )
            assert server.port == 3037
        finally:
            server.stop()
            storage.clear()
            loop.close()

    def test_clear_tokens_on_create(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        storage_pre = FileTokenStorage("http://example.com/mcp")
        storage_pre._write({"tokens": {"access_token": "old", "token_type": "Bearer"}})
        assert storage_pre._path.exists()

        try:
            provider, server, storage = create_oauth_provider(
                "http://example.com/mcp", clear_tokens=True,
            )
            assert not storage._path.exists()
        finally:
            server.stop()
            loop.close()

    def test_no_browser_mode(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            provider, server, storage = create_oauth_provider(
                "http://example.com/mcp", no_browser=True,
            )
            assert provider is not None
        finally:
            server.stop()
            storage.clear()
            loop.close()


# ── CLI integration tests ────────────────────────────────────────────────────


class TestCLIPKCEFlags:
    def test_no_browser_requires_http(self) -> None:
        cmd = f"{sys.executable} {SERVERS_DIR / 'good_server.py'}"
        result = runner.invoke(app, [
            "check", "--stdio", cmd, "--no-browser",
        ])
        assert result.exit_code == 3

    def test_clear_tokens_requires_http(self) -> None:
        cmd = f"{sys.executable} {SERVERS_DIR / 'good_server.py'}"
        result = runner.invoke(app, [
            "check", "--stdio", cmd, "--clear-tokens",
        ])
        assert result.exit_code == 3

    def test_callback_port_requires_http(self) -> None:
        cmd = f"{sys.executable} {SERVERS_DIR / 'good_server.py'}"
        result = runner.invoke(app, [
            "check", "--stdio", cmd, "--callback-port", "3035",
        ])
        assert result.exit_code == 3

    def test_no_auth_requires_http(self) -> None:
        cmd = f"{sys.executable} {SERVERS_DIR / 'good_server.py'}"
        result = runner.invoke(app, [
            "check", "--stdio", cmd, "--no-auth",
        ])
        assert result.exit_code == 3

    def test_bench_pkce_flags_require_http(self) -> None:
        cmd = f"{sys.executable} {SERVERS_DIR / 'good_server.py'}"
        result = runner.invoke(app, [
            "bench", "--stdio", cmd, "--no-auth",
        ])
        assert result.exit_code == 3

    def test_audit_pkce_flags_require_http(self) -> None:
        cmd = f"{sys.executable} {SERVERS_DIR / 'good_server.py'}"
        result = runner.invoke(app, [
            "audit", "--stdio", cmd, "--no-browser",
        ])
        assert result.exit_code == 3

    def test_watch_pkce_flags_require_http(self) -> None:
        cmd = f"{sys.executable} {SERVERS_DIR / 'good_server.py'}"
        result = runner.invoke(app, [
            "watch", "--stdio", cmd, "--clear-tokens",
        ])
        assert result.exit_code == 3

    def test_pin_pkce_flags_require_http(self) -> None:
        cmd = f"{sys.executable} {SERVERS_DIR / 'good_server.py'}"
        result = runner.invoke(app, [
            "pin", "--stdio", cmd, "--callback-port", "3035",
        ])
        assert result.exit_code == 3


class TestMaybeSetupPKCE:
    def test_stdio_returns_none(self) -> None:
        from halflist.cli import _maybe_setup_pkce

        auth, server = _maybe_setup_pkce(
            None, None, no_auth=False, no_browser=False,
            clear_tokens=False, callback_port=None, oauth_scope=None,
        )
        assert auth is None
        assert server is None

    def test_no_auth_returns_none(self) -> None:
        from halflist.cli import _maybe_setup_pkce

        auth, server = _maybe_setup_pkce(
            "http://example.com/mcp", None, no_auth=True, no_browser=False,
            clear_tokens=False, callback_port=None, oauth_scope=None,
        )
        assert auth is None
        assert server is None

    def test_explicit_auth_header_returns_none(self) -> None:
        from halflist.cli import _maybe_setup_pkce

        auth, server = _maybe_setup_pkce(
            "http://example.com/mcp",
            {"Authorization": "Bearer tok123"},
            no_auth=False, no_browser=False,
            clear_tokens=False, callback_port=None, oauth_scope=None,
        )
        assert auth is None
        assert server is None

    def test_http_without_auth_creates_provider(self) -> None:
        from halflist.cli import _maybe_setup_pkce

        auth, server = _maybe_setup_pkce(
            "http://example.com/mcp", None,
            no_auth=False, no_browser=False,
            clear_tokens=False, callback_port=None, oauth_scope=None,
        )
        try:
            assert auth is not None
            assert server is not None
            assert server.port >= 3030
        finally:
            if server:
                server.stop()

    def test_http_with_non_auth_headers_creates_provider(self) -> None:
        from halflist.cli import _maybe_setup_pkce

        auth, server = _maybe_setup_pkce(
            "http://example.com/mcp",
            {"X-Custom": "value"},
            no_auth=False, no_browser=False,
            clear_tokens=False, callback_port=None, oauth_scope=None,
        )
        try:
            assert auth is not None
            assert server is not None
        finally:
            if server:
                server.stop()
