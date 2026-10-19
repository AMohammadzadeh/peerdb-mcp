# PeerDB MCP

[![CI](https://github.com/AMohammadzadeh/peerdb-mcp/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/AMohammadzadeh/peerdb-mcp/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)

**Inspect replication pipelines, investigate sync errors, and manage CDC mirrors from your AI client.**

PeerDB MCP connects your [Model Context Protocol](https://modelcontextprotocol.io/)
client to the PeerDB Flow REST API. Ask about pipeline status, review recent errors
and batches, or request a pipeline change using 13 typed tools.

**Community preview.** MCP integration and API contract tests use a simulated
gateway; live PeerDB compatibility is still being validated. Reports from real
setups are welcome. This is an independent community project.

[Quick start](#quick-start) · [Client setup](docs/clients.md) · [Tool reference](docs/reference.md#tools) · [Troubleshooting](docs/troubleshooting.md) · [Contributing](CONTRIBUTING.md)

## What you can do

| Ask your client… | PeerDB MCP provides… |
| --- | --- |
| “List my replication pipelines and their states.” | Mirror names, source/destination peers, and current states. |
| “Investigate the latest errors for `orders_to_warehouse`.” | Status, recent errors, CDC batches, and heuristic troubleshooting suggestions. |
| “Show the replication slots for `postgres_source`.” | PostgreSQL slot details and lag from PeerDB. |
| “Pause `orders_to_warehouse`, then check its state.” | A pause request and a separate status check, when writes are enabled. |

You can also validate and create CDC mirrors, resume paused pipelines, and update
batch size, idle timeout, snapshot settings, or table mappings. Diagnostics return
evidence and possible next steps; they do not automatically repair replication.

## Quick start

You need a reachable **PeerDB Flow REST gateway**, [uv](https://docs.astral.sh/uv/)
(which includes `uvx`), Git, and an MCP client that supports stdio. The server uses
Python 3.11+; uv can provision a compatible Python when needed.

Add this to your client's MCP configuration. It starts in **read-only mode**:

```json
{
  "mcpServers": {
    "peerdb": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/AMohammadzadeh/peerdb-mcp.git@main",
        "peerdb-mcp"
      ],
      "env": {
        "PEERDB_URL": "http://localhost:8113",
        "PEERDB_READ_ONLY": "true"
      }
    }
  }
}
```

Restart your client, then ask:

> Check the PeerDB version, then list my pipelines. Do not change anything.

The client installs and launches the server automatically. `localhost` refers to
the computer running the MCP process. Point the URL at the **REST gateway**;
PeerDB's UI and gRPC ports serve different interfaces. Port 8113 is a common
self-hosted gateway port—check your deployment.

For client-specific instructions, see [Claude Desktop, Claude Code, Cursor, and Codex](docs/clients.md).
For a fixed revision, replace `@main` with a full commit SHA. Installation currently
uses GitHub; the package has not been published to PyPI.

### Authentication

Set credentials through your client's environment or secure secret mechanism:

| Gateway authentication | Variables to set |
| --- | --- |
| None | Only `PEERDB_URL` |
| Bearer token | `PEERDB_TOKEN` |
| HTTP Basic | Both `PEERDB_USERNAME` and `PEERDB_PASSWORD` |

Choose one authentication method. See the [configuration reference](docs/reference.md#authentication)
for examples and all environment variables. Use HTTPS for remote authenticated
gateways. Pipeline logs and configuration are returned to your MCP client and may
be sent to its model provider; review your client's data handling before use.

### Enable pipeline changes

Set `PEERDB_READ_ONLY` to `false` and restart the MCP process to enable creation,
pause, resume, and updates. The quick start explicitly enables read-only mode;
the application's default when this variable is omitted is `false`.

Changes are asynchronous. An accepted request does not mean the operation has
finished; check pipeline status afterward. See [operation behavior](docs/reference.md#asynchronous-changes-and-diagnostics).

## Supported operations

| Area | Coverage |
| --- | --- |
| Monitoring | Version, peers, CDC/QRep pipeline status, errors, CDC batches, PostgreSQL slots |
| Diagnostics | Per-pipeline evidence and heuristic findings, including partial results |
| CDC management | Validate, create, pause, resume, and update supported settings |
| QRep management | Pause/resume; creation and modification are not implemented |
| Transport | Local stdio, with outbound HTTP(S) to PeerDB |

Peer creation, pipeline deletion, and automatic resync are not exposed.
Managed ClickPipes compatibility has not been verified. Read the
[tool reference](docs/reference.md#tools) for arguments and
[API compatibility notes](docs/reference.md#api-compatibility) for the upstream source checked.

## Verify your local setup

From a checkout on a computer that can reach PeerDB:

```sh
git clone https://github.com/AMohammadzadeh/peerdb-mcp.git
cd peerdb-mcp
uv sync --frozen
export PEERDB_URL=http://localhost:8113
uv run --frozen python -m peerdb_mcp.smoke --pipeline YOUR_EXISTING_MIRROR
```

Inject authentication variables if required. Omit `--pipeline` to check only MCP
startup, version, and pipeline listing. The test forces read-only mode and prints
a summary without URLs, credentials, pipeline names, or log contents. Failed or
partial checks return a nonzero exit status. Passing checks establish API access,
not replication health.

## Feedback and contributions

Trying this with PeerDB? [Report your results](https://github.com/AMohammadzadeh/peerdb-mcp/issues/new?template=bug_report.md)
with your PeerDB version, MCP client, and a sanitized smoke-test summary. Please
remove credentials and private data from anything you share.

Bug fixes, compatibility reports, documentation improvements, and focused feature
requests are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md) for development
commands and the API contract conventions.
