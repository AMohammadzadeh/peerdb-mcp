import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.fixture
def gateway():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            self.respond(None)

        def do_POST(self):
            self.respond(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))

        def respond(self, body):
            calls.append((self.path, body))
            responses = {
                "/v1/version": {"version": "integration-test"},
                "/v1/mirrors/list": {"mirrors": [{"name": "orders", "status": "STATUS_RUNNING"}]},
                "/v1/peers/list": {"items": []},
                "/v1/mirrors/status": {"currentFlowState": "STATUS_RUNNING", "cdcStatus": {}},
                "/v1/mirrors/logs": {"errors": [{"id": 1, "errorMessage": "connection timeout"}]},
                "/v1/mirrors/cdc/batches": {"cdcBatches": []},
                "/v1/peers/slots/source": {"slotData": []},
                "/v1/mirrors/cdc/validate": {},
                "/v1/flows/cdc/create": {"workflowId": "test-workflow"},
                "/v1/mirrors/state_change": {},
            }
            self.send_response(200 if self.path in responses else 404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(responses.get(self.path, {})).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", calls
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


async def test_stdio_end_to_end(gateway):
    url, calls = gateway
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "peerdb_mcp.server"],
        env={"PEERDB_URL": url, "PEERDB_READ_ONLY": "false"},
    )
    async with asyncio.timeout(30), stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {tool.name: tool for tool in (await session.list_tools()).tools}
            assert len(tools) == 13
            assert tools["diagnose_pipeline"].annotations.readOnlyHint
            assert tools["update_pipeline"].annotations.destructiveHint
            assert "ctx" not in tools["get_pipeline_status"].inputSchema["properties"]
            assert tools["get_pipeline_errors"].inputSchema["properties"]["limit"]["maximum"] == 100

            for name, arguments in [
                ("get_peerdb_version", {}),
                ("list_pipelines", {}),
                ("list_peers", {}),
                ("get_pipeline_status", {"name": "orders"}),
                ("get_pipeline_errors", {"name": "orders"}),
                ("get_pipeline_batches", {"name": "orders"}),
                ("get_peer_slots", {"peer_name": "source"}),
                ("diagnose_pipeline", {"name": "orders"}),
                ("pause_pipeline", {"name": "orders"}),
                ("update_pipeline", {"name": "orders", "update": {"batch_size": 50}}),
            ]:
                result = await session.call_tool(name, arguments)
                assert not result.isError, (name, result)
                assert result.structuredContent is not None
                if name == "diagnose_pipeline":
                    assert result.structuredContent["findings"][0]["category"] == "connectivity"

            config = {
                "flow_job_name": "new",
                "source_name": "source",
                "destination_name": "dest",
                "table_mappings": [
                    {"source_table_identifier": "public.x", "destination_table_identifier": "x"}
                ],
            }
            for name in ("validate_pipeline", "create_pipeline"):
                result = await session.call_tool(name, {"config": config})
                assert not result.isError, result

            count = len(calls)
            invalid = await session.call_tool(
                "get_pipeline_errors", {"name": "orders", "limit": 101}
            )
            assert invalid.isError
            assert len(calls) == count
            invalid_update = await session.call_tool(
                "update_pipeline", {"name": "orders", "update": {}}
            )
            assert invalid_update.isError
            assert len(calls) == count


async def test_stdio_read_only(gateway):
    url, calls = gateway
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "peerdb_mcp.server"],
        env={"PEERDB_URL": url, "PEERDB_READ_ONLY": "true"},
    )
    async with asyncio.timeout(30), stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("resume_pipeline", {"name": "orders"})
            assert result.isError
            assert "Writes are disabled" in result.content[0].text
            assert calls == []
            assert not (await session.call_tool("list_pipelines", {})).isError
