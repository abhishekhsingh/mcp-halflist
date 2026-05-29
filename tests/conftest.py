import http.server
import json
import re
import sys
import threading
import urllib.parse
from pathlib import Path

import pytest

SERVERS_DIR = Path(__file__).parent / "servers"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\([A-Za-z]")


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


@pytest.fixture
def good_server_cmd() -> str:
    return f"{sys.executable} {SERVERS_DIR / 'good_server.py'}"


@pytest.fixture
def bad_server_cmd() -> str:
    return f"{sys.executable} {SERVERS_DIR / 'bad_server.py'}"


@pytest.fixture
def poisoned_server_cmd() -> str:
    return f"{sys.executable} {SERVERS_DIR / 'poisoned_server.py'}"


@pytest.fixture
def full_server_cmd() -> str:
    return f"{sys.executable} {SERVERS_DIR / 'full_server.py'}"


class _OAuthTokenHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode()
        params = urllib.parse.parse_qs(body)

        grant_type = params.get("grant_type", [""])[0]
        client_id = params.get("client_id", [""])[0]
        client_secret = params.get("client_secret", [""])[0]

        if grant_type != "client_credentials":
            self._json_response(400, {"error": "unsupported_grant_type"})
            return

        if not client_id or not client_secret:
            self._json_response(401, {"error": "invalid_client"})
            return

        resp: dict[str, object] = {
            "access_token": f"mock-token-{client_id}",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        scope = params.get("scope", [None])[0]
        if scope:
            resp["scope"] = scope

        self._json_response(200, resp)

    def _json_response(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def oauth_server() -> dict[str, str]:
    """Spin up a local OAuth2 mock server. Returns {"url", "client_id", "client_secret"}."""
    server = http.server.HTTPServer(("127.0.0.1", 0), _OAuthTokenHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield {
        "url": f"http://127.0.0.1:{port}/token",
        "client_id": "test-client",
        "client_secret": "test-secret",
    }
    server.shutdown()
