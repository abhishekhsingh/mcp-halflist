from __future__ import annotations

import httpx

from halflist.constants import DEFAULT_TIMEOUT


async def fetch_oauth_token(
    token_url: str,
    client_id: str,
    client_secret: str,
    scope: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Fetch OAuth2 access token via client_credentials grant."""
    data: dict[str, str] = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if scope:
        data["scope"] = scope

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(token_url, data=data)
        response.raise_for_status()
        try:
            body = response.json()
        except Exception as e:
            raise ValueError(
                f"OAuth token endpoint returned non-JSON response (status {response.status_code})"
            ) from e
        token = body.get("access_token")
        if not token:
            raise ValueError("OAuth response missing 'access_token'")
        return token
