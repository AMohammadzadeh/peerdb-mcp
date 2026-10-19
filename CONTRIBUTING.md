# Contributing to PeerDB MCP

Thanks for helping improve PeerDB MCP. Compatibility reports from real deployments
are especially useful while the project is in preview.

## Report a problem or propose a feature

Use [GitHub Issues](https://github.com/AMohammadzadeh/peerdb-mcp/issues) for bugs,
compatibility reports, and feature requests. Explain the workflow you are trying
to complete and include a minimal, sanitized example. For substantial changes,
open an issue first so the implementation can be discussed.

Never include credentials, private URLs, customer data, or unredacted logs.

## Develop locally

Requires Git, Python 3.11+, and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/AMohammadzadeh/peerdb-mcp.git
cd peerdb-mcp
uv sync --frozen
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv build
```

The test suite uses mocked REST responses and real stdio MCP client/server
sessions against a local fake gateway. It needs neither a PeerDB deployment nor
credentials. To format changed Python files, run `uv run --frozen ruff format .`.

To submit changes, fork the repository, create a branch, and open a pull request.
Describe the problem, resulting behavior, and validation performed. Keep changes
focused; a documentation-only change does not need new Python tests.

## Code layout

| File | Responsibility |
| --- | --- |
| `src/peerdb_mcp/server.py` | MCP tool registration and stdio entry point |
| `src/peerdb_mcp/client.py` | HTTP requests, authentication, settings, safe transport errors |
| `src/peerdb_mcp/service.py` | Pipeline operations and diagnostic summaries |
| `src/peerdb_mcp/models.py` | Typed creation/update inputs |
| `src/peerdb_mcp/smoke.py` | Read-only local integration check |
| `tests/` | REST contracts, lifecycle behavior and MCP integration |

## API changes

Verify routes and payloads against PeerDB's protobuf/API definitions. Include the
upstream source or version in your PR. Preserve request bounds, timeout behavior,
authentication, and read-only enforcement. Do not retry mutations automatically.

For new tools, add the appropriate MCP annotations and tests that check the actual
HTTP method, route, payload and failure behavior. Update the
[tool reference](docs/reference.md#tools) and any affected configuration examples.
Keep stdout reserved for MCP protocol traffic.

## Live compatibility reports

Run the [smoke test](README.md#verify-your-local-setup) on a machine that can reach
your PeerDB instance. Report the version, client, authentication method and
sanitized summary. Clearly distinguish automated mock tests from live validation.
Only exercise writes against a pipeline you intend to change.
