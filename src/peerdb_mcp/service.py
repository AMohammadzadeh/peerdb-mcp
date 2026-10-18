"""Pipeline operations and evidence-based diagnostic summaries."""

import asyncio
from urllib.parse import quote

from .client import PeerDBClient, PeerDBError
from .models import CDCConfig, CDCUpdate

STATES = [
    "STATUS_UNKNOWN",
    "STATUS_RUNNING",
    "STATUS_PAUSED",
    "STATUS_PAUSING",
    "STATUS_SETUP",
    "STATUS_SNAPSHOT",
    "STATUS_TERMINATING",
    "STATUS_TERMINATED",
    "STATUS_COMPLETED",
    "STATUS_RESYNC",
    "STATUS_FAILED",
    "STATUS_MODIFYING",
]


def flow_state(status: dict) -> str:
    value = status.get("currentFlowState", status.get("current_flow_state", "STATUS_UNKNOWN"))
    if isinstance(value, int) and 0 <= value < len(STATES):
        return STATES[value]
    return str(value)


class PipelineService:
    def __init__(self, client: PeerDBClient):
        self.client = client

    async def status(self, name: str) -> dict:
        return await self.client.request(
            "POST",
            "/v1/mirrors/status",
            {
                "flow_job_name": name,
                "include_flow_info": True,
                "exclude_batches": True,
                "exclude_snapshot_status": False,
            },
        )

    async def logs(self, name: str, level: str = "error", page: int = 1, limit: int = 20) -> dict:
        return await self.client.request(
            "POST",
            "/v1/mirrors/logs",
            {
                "flow_job_name": name,
                "level": level,
                "page": page,
                "num_per_page": limit,
            },
        )

    async def batches(self, name: str, limit: int = 20, before_id: int = 0) -> dict:
        return await self.client.request(
            "POST",
            "/v1/mirrors/cdc/batches",
            {
                "flow_job_name": name,
                "limit": limit,
                "ascending": False,
                "before_id": str(before_id),
            },
        )

    async def validate(self, config: CDCConfig) -> dict:
        return await self.client.request(
            "POST",
            "/v1/mirrors/cdc/validate",
            {
                "connection_configs": config.model_dump(exclude_none=True),
            },
        )

    async def create(self, config: CDCConfig) -> dict:
        self.client.require_write()
        await self.validate(config)
        result = await self.client.request(
            "POST",
            "/v1/flows/cdc/create",
            {
                "connection_configs": config.model_dump(exclude_none=True),
            },
        )
        return {"accepted": True, "result": result, "next_step": "Check get_pipeline_status."}

    async def change_state(self, name: str, target: str) -> dict:
        self.client.require_write()
        current = flow_state(await self.status(name))
        if current == target:
            return {"accepted": False, "already_in_requested_state": True, "state": current}
        required = "STATUS_RUNNING" if target == "STATUS_PAUSED" else "STATUS_PAUSED"
        if current != required:
            raise PeerDBError(f"Cannot request {target} from {current}; expected {required}.")
        result = await self.client.request(
            "POST",
            "/v1/mirrors/state_change",
            {
                "flow_job_name": name,
                "requested_flow_state": target,
            },
        )
        return {
            "accepted": True,
            "requested_state": target,
            "result": result,
            "next_step": "State changes are asynchronous. Check get_pipeline_status.",
        }

    async def update(self, name: str, update: CDCUpdate) -> dict:
        self.client.require_write()
        status = await self.status(name)
        if "cdcStatus" not in status and "cdc_status" not in status:
            raise PeerDBError("Dynamic updates are supported only for CDC pipelines.")
        current = flow_state(status)
        if current not in {"STATUS_RUNNING", "STATUS_PAUSED"}:
            raise PeerDBError(f"Cannot modify a pipeline in {current}; wait for running or paused.")
        result = await self.client.request(
            "POST",
            "/v1/mirrors/state_change",
            {
                "flow_job_name": name,
                "requested_flow_state": current,
                "flow_config_update": {
                    "cdc_flow_config_update": update.model_dump(exclude_none=True),
                },
            },
        )
        return {
            "accepted": True,
            "state_at_request": current,
            "result": result,
            "next_step": "Update was signaled asynchronously. Check get_pipeline_status.",
        }

    async def diagnose(self, name: str, limit: int = 20) -> dict:
        async def capture(coro):
            try:
                return await coro
            except PeerDBError as exc:
                return {"unavailable": str(exc)}

        status, logs = await asyncio.gather(
            capture(self.status(name)), capture(self.logs(name, limit=limit))
        )
        evidence = {"status": status, "recent_errors": logs}
        if "cdcStatus" in status or "cdc_status" in status:
            evidence["recent_batches"] = await capture(self.batches(name, limit))
        issues = []
        state = flow_state(status)
        if state == "STATUS_FAILED":
            issues.append(
                {"category": "failed", "next_step": "Inspect recent errors and PeerDB worker logs."}
            )
        elif state in {"STATUS_PAUSED", "STATUS_PAUSING"}:
            issues.append(
                {
                    "category": "paused",
                    "next_step": "Replication is paused or pausing; resume only when intended.",
                }
            )
        rules = [
            (
                "authentication",
                ("authentication", "password", "permission denied", "unauthorized"),
                "Check source/destination peer credentials and database grants.",
            ),
            (
                "connectivity",
                ("timeout", "timed out", "connection refused", "connection reset", "no such host"),
                "Check peer reachability, DNS, firewall rules, and database availability.",
            ),
            (
                "replication_slot",
                ("replication slot", "wal segment", "publication"),
                "Inspect the PostgreSQL replication slot, publication, WAL retention and slot lag.",
            ),
            (
                "schema",
                ("schema", "does not exist", "type mismatch", "column"),
                "Compare source and destination schemas and the pipeline table mappings.",
            ),
            (
                "capacity",
                ("disk", "quota", "too many connections", "out of memory"),
                "Check disk space, resource quotas, connection limits and worker capacity.",
            ),
        ]
        for category, patterns, next_step in rules:
            matches = [
                entry.get("id")
                for entry in logs.get("errors", [])
                if any(
                    p in str(entry.get("errorMessage", entry.get("error_message", ""))).lower()
                    for p in patterns
                )
            ]
            if matches:
                issues.append(
                    {"category": category, "matching_log_ids": matches, "next_step": next_step}
                )
        unavailable = [key for key, value in evidence.items() if "unavailable" in value]
        return {
            "pipeline": name,
            "state": state,
            "partial": bool(unavailable),
            "unavailable_checks": unavailable,
            "findings": issues,
            "evidence": evidence,
            "interpretation": (
                "Findings are heuristics over recent errors, which may be historical. "
                "No findings does not establish health; compare batch progress over time. "
                "No corrective action was executed."
            ),
        }

    async def slots(self, peer_name: str) -> dict:
        return await self.client.request("GET", f"/v1/peers/slots/{quote(peer_name, safe='')}")
