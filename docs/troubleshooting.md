# Troubleshooting

[Back to the README](../README.md) · [Client setup](clients.md)

Start with `get_peerdb_version`, then `list_pipelines`. This separates gateway or
authentication problems from problems with a particular mirror.

| Symptom | What to check |
| --- | --- |
| Client cannot find `uvx` | Install uv and Git; set an absolute path to `uvx` in GUI clients that do not inherit your shell's PATH. |
| Server exits during startup | Set `PEERDB_URL`. Use either a bearer token or a complete Basic username/password pair. Check your client's server logs locally. |
| HTTP 401 or 403 | Verify the credentials and their access to the gateway. Basic authentication requires both `PEERDB_USERNAME` and `PEERDB_PASSWORD`; leave `PEERDB_TOKEN` unset. |
| Invalid JSON or unexpected HTML | Confirm the URL points at the Flow REST gateway, not the PeerDB UI, a login page, or a gRPC port. |
| Connection refused or timeout | Test reachability from the computer running the MCP process. Its `localhost` is not another machine. Check the port, VPN, proxy and TLS configuration. |
| HTTP 404 | Check the mirror name and gateway URL, including any reverse-proxy path prefix. Confirm your PeerDB version exposes the requested route. |
| Writes are disabled | Set `PEERDB_READ_ONLY=false` and restart the server only when you intend to change pipelines. |
| State change rejected | Pause requires a running pipeline; resume requires a paused pipeline. Wait for transitional states to finish. |
| An update was accepted but is not visible yet | PeerDB signals changes asynchronously. Check status/configuration again; avoid concurrent lifecycle changes by other operators. |
| Diagnostics report partial results | One or more upstream checks failed. Inspect the returned `unavailable_checks` and evidence before drawing conclusions. |
| No error findings, but data seems stale | Errors may not capture every failure. Compare batch progress over time and verify source/destination data separately. |

## Run the smoke test

Follow [Verify your local setup](../README.md#verify-your-local-setup). The test
starts the real MCP server and makes read-only calls against the configured
PeerDB gateway. Without `--pipeline`, per-mirror checks are skipped. A successful
smoke test does not prove that replication data is complete or consistent.

For local authentication, provide credentials through environment variables or
your client's secret mechanism. `.env.example` documents names; `.env` files are
not loaded automatically.

## Retry behavior

The client does not automatically retry requests or follow HTTP redirects. Set the
final gateway URL directly. After a timed-out mutation, inspect pipeline status
before retrying: PeerDB may already have accepted the original request.

## Report an issue

Include your PeerDB version, operating system, Python/uv version, MCP client,
authentication method (not its credentials), affected tool, and sanitized steps
to reproduce. Use the [bug-report template](https://github.com/AMohammadzadeh/peerdb-mcp/issues/new?template=bug_report.md).
Do not post bearer tokens, Basic credentials, raw pipeline configurations, or
private replication logs. The smoke-test summary is designed for sharing.
