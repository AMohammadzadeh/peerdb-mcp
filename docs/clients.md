# Connect your MCP client

[Back to the README](../README.md) · [Configuration reference](reference.md)

Install [uv](https://docs.astral.sh/uv/) and Git on the computer running your MCP
client. These examples use the same stdio server and start in read-only mode.
They are configuration examples; automated integration tests use the MCP Python
SDK rather than the desktop applications themselves.

## Claude Desktop

Open **Settings → Developer → Edit Config** and merge the following into your
`claude_desktop_config.json`. Preserve any existing servers.

```json
{
  "mcpServers": {
    "peerdb": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/AMohammadzadeh/peerdb-mcp.git@main", "peerdb-mcp"],
      "env": {
        "PEERDB_URL": "http://localhost:8113",
        "PEERDB_READ_ONLY": "true"
      }
    }
  }
}
```

Restart Claude Desktop. If it cannot find `uvx`, set `command` to the absolute
path returned by `which uvx` on macOS/Linux or `where.exe uvx` on Windows.

## Cursor

Merge the JSON configuration above into `.cursor/mcp.json` for a project, or
`~/.cursor/mcp.json` for all projects. Enable the server in Cursor's MCP settings
and restart it after changing environment variables.

## Claude Code

Run this from the project where you want to use PeerDB:

```sh
claude mcp add --transport stdio peerdb \
  --env PEERDB_URL=http://localhost:8113 \
  --env PEERDB_READ_ONLY=true \
  -- uvx --from git+https://github.com/AMohammadzadeh/peerdb-mcp.git@main peerdb-mcp
```

Use `/mcp` inside Claude Code to inspect the connection. Add authentication through
your client's secure configuration if your gateway requires it; avoid putting
secret values in shell command history.

## Codex

Add this to `~/.codex/config.toml`, preserving existing settings:

```toml
[mcp_servers.peerdb]
command = "uvx"
args = ["--from", "git+https://github.com/AMohammadzadeh/peerdb-mcp.git@main", "peerdb-mcp"]

[mcp_servers.peerdb.env]
PEERDB_URL = "http://localhost:8113"
PEERDB_READ_ONLY = "true"
```

Restart Codex after saving. Configure Basic or bearer credentials using the
corresponding environment variables in the [authentication guide](reference.md#authentication).

## Check the connection

Ask your client:

> Use `get_peerdb_version` and `list_pipelines` to check my PeerDB connection.

For an existing mirror:

> Diagnose `YOUR_EXISTING_MIRROR`. Show the evidence and any checks that were unavailable. Do not modify the pipeline.

If the tools are unavailable or a request fails, use the
[troubleshooting guide](troubleshooting.md).

## Use a local checkout

After cloning and running `uv sync --frozen`, replace the command and arguments in
your client configuration with:

```json
{
  "command": "uv",
  "args": ["run", "--directory", "/absolute/path/peerdb-mcp", "--frozen", "peerdb-mcp"],
  "env": {
    "PEERDB_URL": "http://localhost:8113",
    "PEERDB_READ_ONLY": "true"
  }
}
```

For a manual launch in a POSIX shell:

```sh
PEERDB_URL=http://localhost:8113 PEERDB_READ_ONLY=true uvx \
  --from git+https://github.com/AMohammadzadeh/peerdb-mcp.git@main peerdb-mcp
```

A manual launch waits for MCP messages on stdin. This process does not serve an
HTTP page. Normally your MCP client launches it and owns its lifetime.
