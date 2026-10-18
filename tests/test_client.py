import httpx
import pytest

from peerdb_mcp.client import PeerDBClient, PeerDBError, Settings


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
