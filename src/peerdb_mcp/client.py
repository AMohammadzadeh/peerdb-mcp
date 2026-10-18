"""Small asynchronous REST client. Mutations are never automatically retried."""

import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx


class PeerDBError(Exception):
    """A safe error suitable for returning through MCP."""


@dataclass(frozen=True)
class Settings:
    url: str
    token: str | None = field(default=None, repr=False)
    timeout: float = 30
    read_only: bool = False
    username: str | None = field(default=None, repr=False)
    password: str | None = field(default=None, repr=False)

    def __post_init__(self):
        parsed = urlsplit(self.url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "PEERDB_URL must be an HTTP(S) gateway URL without credentials or query"
            )
        if not 0 < self.timeout <= 300:
            raise ValueError("PEERDB_TIMEOUT_SECONDS must be between 0 and 300")
        basic_configured = self.username is not None or self.password is not None
        if basic_configured and (not self.username or not self.password):
            raise ValueError("Set both PEERDB_USERNAME and PEERDB_PASSWORD to non-empty values")
        if self.token and basic_configured:
            raise ValueError("Use PEERDB_TOKEN or Basic authentication, not both")
        if self.username and ":" in self.username:
            raise ValueError("PEERDB_USERNAME cannot contain a colon")

    @classmethod
    def from_env(cls) -> "Settings":
        url = os.environ.get("PEERDB_URL")
        if not url:
            raise ValueError("Set PEERDB_URL to your PeerDB Flow REST gateway")
        read_only = os.environ.get("PEERDB_READ_ONLY", "false").lower()
        if read_only not in {"true", "false"}:
            raise ValueError("PEERDB_READ_ONLY must be true or false")
        return cls(
            url=url,
            token=os.environ.get("PEERDB_TOKEN") or None,
            timeout=float(os.environ.get("PEERDB_TIMEOUT_SECONDS", "30")),
            read_only=read_only == "true",
            username=os.environ.get("PEERDB_USERNAME") or None,
            password=os.environ.get("PEERDB_PASSWORD") or None,
        )


class PeerDBClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        headers = {"Accept": "application/json"}
        if settings.token:
            headers["Authorization"] = f"Bearer {settings.token}"
        auth = None
        if settings.username is not None and settings.password is not None:
            auth = httpx.BasicAuth(settings.username, settings.password)
        self.http = httpx.AsyncClient(
            base_url=settings.url.rstrip("/") + "/",
            headers=headers,
            auth=auth,
            timeout=settings.timeout,
            follow_redirects=False,
            transport=transport,
        )

    async def close(self):
        await self.http.aclose()

    def require_write(self):
        if self.settings.read_only:
            raise PeerDBError("Writes are disabled by PEERDB_READ_ONLY")

    async def request(self, method: str, path: str, body: dict | None = None) -> dict:
        try:
            response = await self.http.request(method, path.lstrip("/"), json=body)
        except httpx.TimeoutException:
            raise PeerDBError(
                "PeerDB request timed out. For a mutation, check pipeline status before retrying; "
                "the operation may have been accepted."
            ) from None
        except httpx.RequestError:
            raise PeerDBError(
                "Cannot reach PeerDB. Check gateway URL, network and TLS settings."
            ) from None
        if not response.is_success:
            hints = {
                400: "Check the request and your PeerDB version's supported fields.",
                401: "Check PEERDB_TOKEN or PEERDB_USERNAME/PEERDB_PASSWORD credentials.",
                403: "Check the configured credentials' access to this PeerDB instance.",
                404: "Check the pipeline name and REST gateway URL.",
                409: "Check current pipeline state before retrying.",
                429: "PeerDB is rate limiting requests; retry later.",
            }
            hint = hints.get(
                response.status_code, "Inspect PeerDB server logs and pipeline status."
            )
            # Do not echo response bodies: upstream errors can contain credentials or SQL data.
            raise PeerDBError(f"PeerDB returned HTTP {response.status_code}. {hint}")
        if response.status_code == 204:
            return {}
        try:
            data = response.json()
        except ValueError:
            raise PeerDBError(
                "PeerDB returned invalid JSON; verify this is the REST gateway."
            ) from None
        if not isinstance(data, dict):
            raise PeerDBError("PeerDB returned an unexpected JSON shape (expected an object).")
        return data
