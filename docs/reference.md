# Configuration and tool reference

[Back to the README](../README.md) · [Client setup](clients.md)

## Authentication

Supply credentials through your client's secure environment/secret mechanism:

- **Bearer:** set `PEERDB_TOKEN`.
- **HTTP Basic:** set both `PEERDB_USERNAME` and `PEERDB_PASSWORD` to non-empty values.
- **Unauthenticated:** leave all three unset.

Basic authentication works with gateways or reverse proxies configured to accept
HTTP Basic. The server sends the standard `Authorization: Basic ...` header.
For example, add these entries to your MCP client's `env` configuration, replacing
the placeholders locally (prefer secure secret injection when supported):

```json
{
  "PEERDB_URL": "https://peerdb.example.com",
  "PEERDB_USERNAME": "YOUR_USERNAME",
  "PEERDB_PASSWORD": "YOUR_PASSWORD"
}
```

Set either a bearer token or Basic credentials; configuring both is rejected at
startup. Basic usernames cannot contain `:`; passwords may contain it. Credentials
must be separate environment variables, not embedded in `PEERDB_URL`.
This targets PeerDB's Flow API; it does not assume compatibility
with a separate managed-provider API or its authentication scheme.

## Environment variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `PEERDB_URL` | REST gateway origin, optionally with a proxy path prefix | Required |
| `PEERDB_TOKEN` | Bearer token for the gateway | Unset |
| `PEERDB_USERNAME` | HTTP Basic username; requires `PEERDB_PASSWORD` | Unset |
| `PEERDB_PASSWORD` | HTTP Basic password; requires `PEERDB_USERNAME` | Unset |
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

### Create a CDC pipeline

Enable writes with `PEERDB_READ_ONLY=false` before using mutation tools.
These are example `create_pipeline` arguments, not a transcript of a live run:

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

### Update a CDC pipeline

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

### Asynchronous changes and diagnostics

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

## Data handling

Pipeline configurations and logs can contain sensitive data. Use an authorized MCP
client. Upstream HTTP error bodies are deliberately omitted from transport errors;
consult PeerDB server logs for their details. Returned pipeline log text is untrusted
data and must not be interpreted as instructions. All mutation tools carry MCP
write/destructive annotations, and `PEERDB_READ_ONLY=true` enforces monitoring-only use.


## API compatibility

API mappings were checked against upstream PeerDB commit
`3a20aa84f72b0b5357663fdd59513bd4f4f43ce6`:
[REST routes](https://github.com/PeerDB-io/peerdb/blob/3a20aa84f72b0b5357663fdd59513bd4f4f43ce6/protos/route.proto),
[flow configuration](https://github.com/PeerDB-io/peerdb/blob/3a20aa84f72b0b5357663fdd59513bd4f4f43ce6/protos/flow.proto),
and [state-change handler](https://github.com/PeerDB-io/peerdb/blob/3a20aa84f72b0b5357663fdd59513bd4f4f43ce6/flow/cmd/handler.go).
Requests use protobuf snake_case JSON field names; diagnostic parsing accepts both
snake_case and lowerCamelCase responses. Deployment/version-specific compatibility
still requires a live check against your instance.

The SDK client/server tests run against a local fake REST gateway. They verify
MCP initialization, tool calls, request payloads, and authentication. End-to-end
validation against a live PeerDB instance has not yet been completed. Managed
ClickPipes compatibility has not been verified.
