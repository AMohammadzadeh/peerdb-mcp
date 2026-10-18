import base64

import httpx
import pytest

from peerdb_mcp.client import PeerDBClient, PeerDBError, Settings


async def test_basic_auth_and_secret_safe_errors():
    username, password = "test-user", "test:password"
    encoded = base64.b64encode(f"{username}:{password}".encode()).decode()

    def handler(request):
        assert request.headers["Authorization"] == f"Basic {encoded}"
        return httpx.Response(401, text=f"Rejected {username}:{password} ({encoded})")

    settings = Settings("https://example.test", username=username, password=password)
    client = PeerDBClient(settings, httpx.MockTransport(handler))
    try:
        with pytest.raises(PeerDBError, match="PEERDB_USERNAME/PEERDB_PASSWORD") as error:
            await client.request("GET", "/v1/version")
        for secret in (username, password, encoded):
            assert secret not in repr(settings)
            assert secret not in str(error.value)
    finally:
        await client.close()


@pytest.mark.parametrize(
    "credentials",
    [
        {"username": "user"},
        {"password": "password"},
        {"username": "user", "password": ""},
        {"username": "", "password": "password"},
        {"username": "user", "password": "password", "token": "token"},
        {"username": "user:name", "password": "password"},
    ],
)
def test_invalid_auth_configuration(credentials):
    with pytest.raises(ValueError):
        Settings("https://example.test", **credentials)


def test_basic_auth_from_environment(monkeypatch):
    monkeypatch.setenv("PEERDB_URL", "https://example.test")
    monkeypatch.delenv("PEERDB_TOKEN", raising=False)
    monkeypatch.setenv("PEERDB_USERNAME", "user")
    monkeypatch.setenv("PEERDB_PASSWORD", "password")
    settings = Settings.from_env()
    assert settings.username == "user"
    assert settings.password == "password"
    monkeypatch.setenv("PEERDB_TOKEN", "token")
    with pytest.raises(ValueError, match="not both"):
        Settings.from_env()


async def test_basic_auth_does_not_follow_redirects():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://other.test"})

    client = PeerDBClient(
        Settings("https://example.test", username="user", password="password"),
        httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(PeerDBError, match="HTTP 302"):
            await client.request("GET", "/v1/version")
        assert len(requests) == 1
    finally:
        await client.close()


async def test_auth_and_proxy_prefix():
    def handler(request):
        assert request.url == "https://example.test/peerdb/v1/version"
        assert request.headers["Authorization"] == "Bearer test-secret"
        return httpx.Response(200, json={"version": "test"})

    client = PeerDBClient(
        Settings("https://example.test/peerdb", "test-secret"), httpx.MockTransport(handler)
    )
    try:
        assert await client.request("GET", "/v1/version") == {"version": "test"}
        assert "test-secret" not in repr(client.settings)
    finally:
        await client.close()


@pytest.mark.parametrize("status", [301, 400, 401, 403, 404, 409, 429, 500, 503])
async def test_http_errors_do_not_leak_body_or_retry(status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status, text="password=secret", headers={"Location": "https://other.test"}
        )

    client = PeerDBClient(Settings("https://example.test"), httpx.MockTransport(handler))
    try:
        with pytest.raises(PeerDBError, match=f"HTTP {status}") as error:
            await client.request("POST", "/v1/flows/cdc/create", {})
        assert "secret" not in str(error.value)
        assert len(requests) == 1
    finally:
        await client.close()


@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, httpx.ConnectError])
async def test_network_errors_are_safe(error_type):
    def handler(request):
        raise error_type("private credentials in internal exception", request=request)

    client = PeerDBClient(Settings("https://example.test"), httpx.MockTransport(handler))
    try:
        with pytest.raises(PeerDBError) as error:
            await client.request("GET", "/v1/version")
        assert "private credentials" not in str(error.value)
    finally:
        await client.close()


@pytest.mark.parametrize("body", [b"<html>wrong server</html>", b"[]", b"null"])
async def test_bad_response(body):
    client = PeerDBClient(
        Settings("https://example.test"),
        httpx.MockTransport(lambda _: httpx.Response(200, content=body)),
    )
    try:
        with pytest.raises(PeerDBError):
            await client.request("GET", "/v1/version")
    finally:
        await client.close()


@pytest.mark.parametrize(
    "url",
    ["", "file:///tmp/test", "https://user:pass@example.test", "https://example.test?token=x"],
)
def test_settings_reject_unsafe_url(url):
    with pytest.raises(ValueError):
        Settings(url)


def test_env_requires_url(monkeypatch):
    monkeypatch.delenv("PEERDB_URL", raising=False)
    with pytest.raises(ValueError, match="PEERDB_URL"):
        Settings.from_env()
