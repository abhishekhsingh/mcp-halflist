from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

_PORT_RANGE = range(3030, 3040)


class CallbackServer:
    """Localhost HTTP server to capture OAuth redirect callbacks.

    Binds to 127.0.0.1 only. Tries ports 3030-3039 unless a specific
    port is requested.
    """

    def __init__(self, port: int | None = None) -> None:
        self._future: asyncio.Future[tuple[str, str | None]] | None = None
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int = 0
        self._requested_port = port

    @property
    def redirect_uri(self) -> str:
        return f"http://127.0.0.1:{self.port}/callback"

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._future = loop.create_future()
        future = self._future

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self_handler) -> None:  # noqa: N802
                parsed = urlparse(self_handler.path)
                if parsed.path != "/callback":
                    self_handler.send_response(404)
                    self_handler.end_headers()
                    return

                params = parse_qs(parsed.query)
                code = params.get("code", [None])[0]
                state = params.get("state", [None])[0]
                error = params.get("error", [None])[0]

                if error:
                    self_handler.send_response(200)
                    self_handler.send_header("Content-Type", "text/html")
                    self_handler.end_headers()
                    self_handler.wfile.write(
                        b"<html><body><h2>Authorization failed.</h2>"
                        b"<p>You can close this window.</p></body></html>"
                    )
                    if not future.done():
                        loop.call_soon_threadsafe(
                            future.set_exception,
                            RuntimeError(f"OAuth authorization error: {error}"),
                        )
                    return

                self_handler.send_response(200)
                self_handler.send_header("Content-Type", "text/html")
                self_handler.end_headers()
                self_handler.wfile.write(
                    b"<html><body><h2>Authorization successful!</h2>"
                    b"<p>You can close this window and return to the terminal.</p></body></html>"
                )

                if not future.done():
                    loop.call_soon_threadsafe(future.set_result, (code or "", state))

            def log_message(self_handler, format: str, *args: object) -> None:
                pass

        ports = [self._requested_port] if self._requested_port else list(_PORT_RANGE)

        for p in ports:
            try:
                self._server = HTTPServer(("127.0.0.1", p), Handler)
                self.port = p
                break
            except OSError:
                continue
        else:
            lo, hi = ports[0], ports[-1]
            raise RuntimeError(f"Could not bind callback server to any port in {lo}-{hi}")

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    async def wait_for_callback(self) -> tuple[str, str | None]:
        assert self._future is not None
        return await self._future

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None


class FileTokenStorage:
    """Persistent token storage at ~/.halflist/tokens/{url_hash}.json.

    File permissions: 0o600. Directory permissions: 0o700.
    Implements the ``mcp.client.auth.TokenStorage`` protocol.
    """

    def __init__(self, server_url: str) -> None:
        url_hash = hashlib.sha256(server_url.encode()).hexdigest()[:16]
        self._dir: Path | None = Path.home() / ".halflist" / "tokens"
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            self._dir.chmod(0o700)
        except OSError:
            logging.getLogger("halflist").warning(
                "Cannot create token directory %s; tokens will not be cached", self._dir,
            )
            self._dir = None
        self._path: Path | None = self._dir / f"{url_hash}.json" if self._dir else None

    def _read(self) -> dict[str, Any]:
        if self._path is None or not self._path.exists():
            return {}
        return json.loads(self._path.read_text())

    def _write(self, data: dict[str, Any]) -> None:
        if self._path is None:
            return
        fd, tmp = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            os.chmod(tmp, 0o600)
            os.rename(tmp, self._path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    async def get_tokens(self) -> OAuthToken | None:
        data = self._read()
        raw = data.get("tokens")
        if not raw:
            return None
        return OAuthToken(**raw)

    async def set_tokens(self, tokens: OAuthToken) -> None:
        data = self._read()
        data["tokens"] = tokens.model_dump(mode="json")
        self._write(data)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        data = self._read()
        raw = data.get("client_info")
        if not raw:
            return None
        return OAuthClientInformationFull(**raw)

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        data = self._read()
        data["client_info"] = client_info.model_dump(mode="json")
        self._write(data)

    def clear(self) -> None:
        if self._path is not None and self._path.exists():
            self._path.unlink()


async def open_browser_handler(url: str) -> None:
    """Open the authorization URL in the default browser."""
    webbrowser.open(url)


async def _headless_callback(
    callback_server: CallbackServer,
) -> tuple[str, str | None]:
    """Race between the callback server and stdin code entry.

    In headless mode, the user may paste the full callback URL into stdin
    if their browser cannot reach 127.0.0.1.
    """
    from rich.console import Console

    c = Console(stderr=True)
    c.print("  [dim]Waiting for callback... or paste the callback URL below:[/dim]")

    loop = asyncio.get_event_loop()

    async def _read_stdin() -> tuple[str, str | None]:
        line: str = await loop.run_in_executor(None, sys.stdin.readline)
        line = line.strip()
        if not line:
            raise RuntimeError("Empty input")
        parsed = urlparse(line)
        params = parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        if code:
            return (code, state)
        return (line, None)

    server_task = asyncio.create_task(callback_server.wait_for_callback())
    stdin_task = asyncio.create_task(_read_stdin())

    done, pending = await asyncio.wait(
        {server_task, stdin_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    return done.pop().result()


async def _print_url_handler(url: str) -> None:
    """Print the authorization URL for headless / --no-browser mode."""
    from rich.console import Console

    c = Console(stderr=True)
    c.print("\n  [bold]Open this URL in your browser to authorize:[/bold]")
    c.print(f"  [blue]{url}[/blue]\n")


def create_oauth_provider(
    server_url: str,
    *,
    callback_port: int | None = None,
    no_browser: bool = False,
    scope: str | None = None,
    clear_tokens: bool = False,
) -> tuple[OAuthClientProvider, CallbackServer, FileTokenStorage]:
    """Build an OAuthClientProvider with a CallbackServer.

    The caller must call ``callback_server.stop()`` when done.

    Returns ``(provider, callback_server, storage)``.
    """
    storage = FileTokenStorage(server_url)

    if clear_tokens:
        storage.clear()

    callback_server = CallbackServer(port=callback_port)
    loop = asyncio.get_event_loop()
    callback_server.start(loop)

    redirect_uri = callback_server.redirect_uri

    metadata = OAuthClientMetadata(
        redirect_uris=[redirect_uri],
        token_endpoint_auth_method="none",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope=scope,
        client_name="halflist",
    )

    if no_browser:
        redirect_handler = _print_url_handler

        async def headless_callback() -> tuple[str, str | None]:
            return await _headless_callback(callback_server)

        callback_handler = headless_callback
    else:
        redirect_handler = open_browser_handler
        callback_handler = callback_server.wait_for_callback

    provider = OAuthClientProvider(
        server_url=server_url,
        client_metadata=metadata,
        storage=storage,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
    )

    return provider, callback_server, storage
