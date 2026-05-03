#!/usr/bin/env python3
"""Standalone OAuth2 mock server for testing halflist --oauth-* flags.

Usage:
    python scripts/oauth_server.py              # port 9090
    python scripts/oauth_server.py --port 8888  # custom port

Token endpoint:  http://localhost:9090/token
Grant type:      client_credentials
Any client_id / client_secret pair works (both must be non-empty).
Returns:         {"access_token": "mock-token-<client_id>", ...}
"""
from __future__ import annotations

import argparse
import http.server
import json
import urllib.parse


class OAuthTokenHandler(http.server.BaseHTTPRequestHandler):
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


def main() -> None:
    parser = argparse.ArgumentParser(description="OAuth2 mock server")
    parser.add_argument("--port", type=int, default=9090)
    args = parser.parse_args()

    server = http.server.HTTPServer(("127.0.0.1", args.port), OAuthTokenHandler)
    print(f"OAuth2 mock server running on http://127.0.0.1:{args.port}/token")
    print("  grant_type:    client_credentials")
    print("  client_id:     any non-empty string")
    print("  client_secret: any non-empty string")
    print("  Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
