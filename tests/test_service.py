import json

import httpx
import pytest
from pydantic import ValidationError

from peerdb_mcp.client import PeerDBClient, PeerDBError, Settings
from peerdb_mcp.models import CDCConfig, CDCUpdate
from peerdb_mcp.service import PipelineService


@pytest.fixture
def config():
    return CDCConfig(
        flow_job_name="orders",
        source_name="source",
        destination_name="destination",
        table_mappings=[
            {"source_table_identifier": "public.orders", "destination_table_identifier": "orders"}
        ],
    )


@pytest.fixture
async def api():
    calls = []
    responses = {}

    def handler(request):
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        result = responses.get(request.url.path, {})
        if isinstance(result, httpx.Response):
            return result
        return httpx.Response(200, json=result)

    client = PeerDBClient(Settings("https://peerdb.test"), httpx.MockTransport(handler))
    yield PipelineService(client), calls, responses
    await client.close()


async def test_create_validates_first(api, config):
    service, calls, responses = api
    responses["/v1/flows/cdc/create"] = {"workflowId": "workflow"}
    result = await service.create(config)
    assert result["accepted"] is True
    assert result["result"]["workflowId"] == "workflow"
    assert [c[1] for c in calls] == ["/v1/mirrors/cdc/validate", "/v1/flows/cdc/create"]
    assert calls[1][2] == {"connection_configs": config.model_dump(exclude_none=True)}


async def test_create_stops_on_validation_failure(api, config):
    service, calls, responses = api
    responses["/v1/mirrors/cdc/validate"] = httpx.Response(400)
    with pytest.raises(PeerDBError):
        await service.create(config)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "current,target", [("STATUS_RUNNING", "STATUS_PAUSED"), (2, "STATUS_RUNNING")]
)
async def test_lifecycle_payload(api, current, target):
    service, calls, responses = api
    responses["/v1/mirrors/status"] = {"currentFlowState": current}
    result = await service.change_state("orders", target)
    assert result["accepted"]
    assert calls[-1] == (
        "POST",
        "/v1/mirrors/state_change",
        {
            "flow_job_name": "orders",
            "requested_flow_state": target,
        },
    )


async def test_lifecycle_noop_and_invalid_state(api):
    service, calls, responses = api
    responses["/v1/mirrors/status"] = {"current_flow_state": "STATUS_PAUSED"}
    assert (await service.change_state("orders", "STATUS_PAUSED"))["already_in_requested_state"]
    responses["/v1/mirrors/status"] = {"currentFlowState": "STATUS_FAILED"}
    with pytest.raises(PeerDBError, match="expected STATUS_PAUSED"):
        await service.change_state("orders", "STATUS_RUNNING")
    assert all(call[1] == "/v1/mirrors/status" for call in calls)


@pytest.mark.parametrize("state", ["STATUS_RUNNING", "STATUS_PAUSED"])
async def test_update_preserves_observed_state(api, state):
    service, calls, responses = api
    responses["/v1/mirrors/status"] = {"currentFlowState": state, "cdcStatus": {}}
    await service.update("orders", CDCUpdate(batch_size=500, idle_timeout=30))
    assert calls[-1][2] == {
        "flow_job_name": "orders",
        "requested_flow_state": state,
        "flow_config_update": {"cdc_flow_config_update": {"batch_size": 500, "idle_timeout": 30}},
    }


@pytest.mark.parametrize(
    "status",
    [
        {"currentFlowState": "STATUS_FAILED", "cdcStatus": {}},
        {"currentFlowState": "STATUS_RUNNING", "qrepStatus": {}},
    ],
)
async def test_reject_unsupported_update(api, status):
    service, calls, responses = api
    responses["/v1/mirrors/status"] = status
    with pytest.raises(PeerDBError):
        await service.update("orders", CDCUpdate(batch_size=500))
    assert len(calls) == 1


async def test_readonly_blocks_every_mutation_before_network(config):
    def unexpected(_):
        pytest.fail("Read-only mutation reached the network")

    client = PeerDBClient(
        Settings("https://peerdb.test", read_only=True), httpx.MockTransport(unexpected)
    )
    service = PipelineService(client)
    try:
        for operation in [
            service.create(config),
            service.change_state("orders", "STATUS_PAUSED"),
            service.change_state("orders", "STATUS_RUNNING"),
            service.update("orders", CDCUpdate(batch_size=10)),
        ]:
            with pytest.raises(PeerDBError, match="Writes are disabled"):
                await operation
    finally:
        await client.close()


async def test_pagination_contract(api):
    service, calls, _ = api
    await service.logs("orders", "warn", 2, 50)
    await service.batches("orders", 10, 123)
    assert calls[0][2] == {
        "flow_job_name": "orders",
        "level": "warn",
        "page": 2,
        "num_per_page": 50,
    }
    assert calls[1][2] == {
        "flow_job_name": "orders",
        "limit": 10,
        "ascending": False,
        "before_id": "123",
    }


async def test_diagnostics_partial_with_evidence(api):
    service, calls, responses = api
    responses["/v1/mirrors/status"] = {"currentFlowState": "STATUS_FAILED", "cdcStatus": {}}
    responses["/v1/mirrors/logs"] = {
        "errors": [
            {"id": 1, "errorMessage": "replication slot lost WAL segment"},
            {"id": 2, "error_message": "connection refused"},
        ]
    }
    responses["/v1/mirrors/cdc/batches"] = httpx.Response(503)
    result = await service.diagnose("orders")
    assert result["partial"]
    assert result["unavailable_checks"] == ["recent_batches"]
    assert {finding["category"] for finding in result["findings"]} == {
        "failed",
        "replication_slot",
        "connectivity",
    }
    assert result["evidence"]["recent_errors"]["errors"][0]["id"] == 1
    assert not any("state_change" in call[1] for call in calls)


async def test_qrep_diagnosis_skips_cdc_batches(api):
    service, calls, responses = api
    responses["/v1/mirrors/status"] = {"current_flow_state": "STATUS_RUNNING", "qrep_status": {}}
    result = await service.diagnose("orders")
    assert not result["partial"]
    assert result["findings"] == []
    assert "does not establish health" in result["interpretation"]
    assert len(calls) == 2


async def test_diagnosis_when_gateway_unavailable(api):
    service, _, responses = api
    responses["/v1/mirrors/status"] = httpx.Response(401)
    responses["/v1/mirrors/logs"] = httpx.Response(401)
    result = await service.diagnose("orders")
    assert result["partial"]
    assert result["state"] == "STATUS_UNKNOWN"
    assert result["unavailable_checks"] == ["status", "recent_errors"]
    assert result["findings"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"batch_size": 0},
        {"batch_size": -1},
        {"unsupported": 1},
        {"skip_initial_snapshot_for_table_additions": True},
    ],
)
def test_invalid_updates(payload):
    with pytest.raises(ValidationError):
        CDCUpdate(**payload)


def test_conflicting_tables():
    table = {"source_table_identifier": "public.x", "destination_table_identifier": "x"}
    with pytest.raises(ValidationError, match="added and removed"):
        CDCUpdate(additional_tables=[table], removed_tables=[table])
