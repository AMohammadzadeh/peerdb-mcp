"""Run a read-only MCP smoke test locally without printing upstream data."""

import argparse
import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .client import Settings


async def check(pipeline: str | None) -> tuple[dict, int]:
    Settings.from_env()  # Validate before launching a child; do not print settings.
    report = {"read_only": True, "checks": {}}
    checks = report["checks"]
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "peerdb_mcp.server"],
        env={**os.environ, "PEERDB_READ_ONLY": "true"},
    )
    # SDK/server stderr can include endpoint names or failed tool arguments.
    with open(os.devnull, "w") as errlog:
        async with asyncio.timeout(180), stdio_client(parameters, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                checks["mcp_connection"] = "passed"
                report["tool_count"] = len(tools)

                async def call(name, arguments=None):
                    result = await session.call_tool(name, arguments or {})
                    if result.isError or not isinstance(result.structuredContent, dict):
                        checks[name] = "failed"
                        return None
                    checks[name] = "passed"
                    return result.structuredContent

                await call("get_peerdb_version")
                listing = await call("list_pipelines")
                if listing is not None:
                    report["pipeline_count"] = len(listing.get("mirrors", []))
                if pipeline:
                    await call("get_pipeline_status", {"name": pipeline})
                    errors = await call("get_pipeline_errors", {"name": pipeline, "limit": 10})
                    if errors is not None:
                        report["recent_error_count"] = len(errors.get("errors", []))
                    diagnosis = await call("diagnose_pipeline", {"name": pipeline, "limit": 10})
                    if diagnosis is not None:
                        report["diagnostic_finding_count"] = len(diagnosis.get("findings", []))
                        if diagnosis.get("partial"):
                            checks["diagnose_pipeline"] = "partial"
                else:
                    checks["pipeline_checks"] = "skipped: supply --pipeline to test a mirror"
    report["note"] = "Checks test API/MCP access, not replication health. No writes were requested."
    return report, int(any(value in {"failed", "partial"} for value in checks.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipeline", help="Existing mirror to inspect; no mutations are performed")
    args = parser.parse_args()
    try:
        report, code = asyncio.run(check(args.pipeline))
    except ValueError:
        report, code = {"error": "Invalid configuration. Check PEERDB_URL and timeout settings."}, 1
    except Exception:
        # Exception groups from the MCP transport may contain sensitive child output.
        report, code = (
            {"error": "MCP smoke test could not complete. Check local setup/connectivity."},
            1,
        )
    print(json.dumps(report, indent=2))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
