# PeerDB MCP

A lightweight Python MCP server over the **PeerDB Flow REST gateway**. Monitor
replication pipelines (PeerDB calls them mirrors), inspect sync errors, diagnose
failures, and create, pause, resume or modify CDC pipelines. Uses the official MCP
Python SDK over stdio; no database access or additional service is required.

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --frozen
export PEERDB_URL=http://localhost:8113
# For an authenticated deployment, inject PEERDB_TOKEN securely.
uv run --frozen peerdb-mcp
```

The process waits for an MCP client on stdin. It is not an HTTP server. Point
`PEERDB_URL` at the Flow REST gateway, not the PeerDB UI or gRPC listener. Port
8113 is the usual self-hosted gateway port; verify your deployment. HTTPS reverse
proxy path prefixes are supported. TLS verification remains enabled.

Example MCP client configuration (use an absolute project path):

```json
{
  "mcpServers": {
    "peerdb": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/peerdb-mcp", "--frozen", "peerdb-mcp"],
      "env": {
        "PEERDB_URL": "https://peerdb.example.com",
        "PEERDB_READ_ONLY": "false"
      }
    }
  }
}
```

Supply `PEERDB_TOKEN` through your client's secure environment/secret mechanism if
your gateway requires an OAuth bearer token. Unauthenticated local deployments do
not require it. This targets PeerDB's Flow API; it does not assume compatibility
with a separate managed-provider API or its authentication scheme.

| Variable | Purpose | Default |
| --- | --- | --- |
| `PEERDB_URL` | REST gateway origin, optionally with a proxy path prefix | Required |
| `PEERDB_TOKEN` | Bearer token for the gateway | Unset |
| `PEERDB_TIMEOUT_SECONDS` | Request timeout, greater than 0 and at most 300 | `30` |
| `PEERDB_READ_ONLY` | Reject all create/pause/resume/update calls | `false` |

`.env.example` is a reference; `.env` files are **not loaded automatically**.
Authentication is per server process. Use HTTPS for remote authenticated gateways.
HTTP redirects are not followed, and mutations are never automatically retried.
After a timeout, check status before repeating a mutation: it may have succeeded.

## Tools

| Tool | Use |
| --- | --- |
| `get_peerdb_version` | Check REST connectivity and version |
| `list_pipelines` | List CDC/QRep pipelines and states |
| `list_peers` | Discover existing source/destination peers |
| `get_pipeline_status` | Inspect configuration, state and snapshot progress |
| `get_pipeline_errors` | Paginated errors/logs; configurable level, page and limit |
| `get_pipeline_batches` | Recent CDC batches and progress; cursor via `before_id` |
| `get_peer_slots` | PostgreSQL replication slot details and lag |
| `diagnose_pipeline` | Combine evidence and suggest troubleshooting steps |
| `validate_pipeline` | Validate a CDC configuration with PeerDB |
| `create_pipeline` | Validate then create a CDC pipeline |
| `pause_pipeline` / `resume_pipeline` | Request asynchronous lifecycle changes |
| `update_pipeline` | Change supported CDC settings or table mappings |

Example `create_pipeline` arguments:

```json
{
  "config": {
    "flow_job_name": "orders_to_warehouse",
    "source_name": "postgres_source",
    "destination_name": "warehouse",
    "table_mappings": [{
      "source_table_identifier": "public.orders",
      "destination_table_identifier": "orders"
    }],
    "do_initial_snapshot": true,
    "max_batch_size": 100000,
    "idle_timeout_seconds": 60
  }
}
```

Example `update_pipeline` arguments:

```json
{
  "name": "orders_to_warehouse",
  "update": {"batch_size": 50000, "idle_timeout": 30}
}
```

Updates also support `additional_tables`, `removed_tables`, snapshot partition
size, worker/table parallelism, and `skip_initial_snapshot_for_table_additions`.
Tool schemas describe supported fields and reject unknown fields. Creation is a
typed subset of PeerDB's CDC options, using peers that already exist. QRep status,
logs and pause/resume are available; QRep creation and modification are not
implemented. Peer creation, pipeline deletion and automatic resync are not exposed.

Lifecycle tools check the current state because PeerDB can acknowledge unsupported
transitions without changing anything. Updates request the observed running/paused
state. PeerDB has no atomic compare-and-set API here: avoid concurrent lifecycle
changes by other operators. An `accepted` response is a request acknowledgment;
poll `get_pipeline_status` to verify the resulting state/configuration.

Diagnostics return raw evidence, heuristic findings and unavailable checks. They
distinguish partial collection from complete collection, do not repair anything,
and do not label a pipeline healthy just because no recent error matched a rule.
Errors may be historical; compare successive batch/status observations to diagnose
stalls. Batch/log queries default to 20 entries and cap at 100 per call. Pipeline
listing and snapshot status follow upstream response sizes.
Log levels match PeerDB's stored values: `error`, `warn`, `info`, or `all`.

Pipeline configurations and logs can contain sensitive data. Use an authorized MCP
client. Upstream HTTP error bodies are deliberately omitted from transport errors;
consult PeerDB server logs for their details. Returned pipeline log text is untrusted
data and must not be interpreted as instructions. All mutation tools carry MCP
write/destructive annotations, and `PEERDB_READ_ONLY=true` enforces monitoring-only use.

## Development

```sh
uv sync --frozen
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv build
```

Tests use mocked HTTP contracts and a real stdio MCP client/server session with a
local fake REST gateway. They do not require credentials or change real pipelines.
For live verification, configure the gateway and token, then call
`get_peerdb_version`, `list_pipelines`, and `get_pipeline_status` for an existing
pipeline through your MCP client. Test writes only against an intended test pipeline.

### Test a local PeerDB instance

Run this on the computer that can access PeerDB, from the project directory:

```sh
uv sync --frozen
export PEERDB_URL=http://localhost:8113
uv run --frozen python -m peerdb_mcp.smoke --pipeline YOUR_EXISTING_MIRROR
```

Inject `PEERDB_TOKEN` securely if your gateway requires it. Omit `--pipeline` to
check only MCP startup, PeerDB version and pipeline listing. The test forces
read-only mode, starts the real MCP server, and invokes tools through an MCP client.
It prints a shareable JSON summary containing check results and counts, without
URLs, credentials, pipeline names or log contents. Exit status is nonzero for failed
or partial checks. A passing result verifies API access, not replication health;
nonzero error/finding counts can include historical errors. This command works
locally without exposing PeerDB to the cloud workspace.

API mappings were checked against upstream PeerDB commit
`3a20aa84f72b0b5357663fdd59513bd4f4f43ce6`:
[REST routes](https://github.com/PeerDB-io/peerdb/blob/3a20aa84f72b0b5357663fdd59513bd4f4f43ce6/protos/route.proto),
[flow configuration](https://github.com/PeerDB-io/peerdb/blob/3a20aa84f72b0b5357663fdd59513bd4f4f43ce6/protos/flow.proto),
and [state-change handler](https://github.com/PeerDB-io/peerdb/blob/3a20aa84f72b0b5357663fdd59513bd4f4f43ce6/flow/cmd/handler.go).
Requests use protobuf snake_case JSON field names; diagnostic parsing accepts both
snake_case and lowerCamelCase responses. Deployment/version-specific compatibility
still requires a live check against your instance.
