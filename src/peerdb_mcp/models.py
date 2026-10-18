"""A typed subset of PeerDB's protobuf JSON request contract."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

Name = Annotated[str, Field(min_length=1, max_length=256, pattern=r"^\S(?:.*\S)?$")]
Positive = Annotated[int, Field(gt=0, le=4294967295)]
Limit = Annotated[int, Field(ge=1, le=100)]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TableMapping(RequestModel):
    source_table_identifier: Name
    destination_table_identifier: Name
    exclude: list[str] = Field(default_factory=list)
    partition_key: str | None = None


class CDCConfig(RequestModel):
    flow_job_name: Name
    source_name: Name
    destination_name: Name
    table_mappings: list[TableMapping] = Field(min_length=1)
    do_initial_snapshot: bool = True
    max_batch_size: Positive | None = None
    idle_timeout_seconds: Positive | None = None
    publication_name: str | None = None
    replication_slot_name: str | None = None
    snapshot_num_rows_per_partition: Positive | None = None
    snapshot_max_parallel_workers: Positive | None = None
    snapshot_num_tables_in_parallel: Positive | None = None
    soft_delete_col_name: str | None = None
    synced_at_col_name: str | None = None


class CDCUpdate(RequestModel):
    batch_size: Positive | None = None
    idle_timeout: Positive | None = None
    additional_tables: list[TableMapping] | None = None
    removed_tables: list[TableMapping] | None = None
    snapshot_num_rows_per_partition: Positive | None = None
    snapshot_max_parallel_workers: Positive | None = None
    snapshot_num_tables_in_parallel: Positive | None = None
    skip_initial_snapshot_for_table_additions: bool | None = None

    @model_validator(mode="after")
    def meaningful_update(self) -> "CDCUpdate":
        values = self.model_dump(exclude_none=True)
        meaningful = {
            k: v for k, v in values.items() if k != "skip_initial_snapshot_for_table_additions"
        }
        if not any(meaningful.values()):
            raise ValueError("Provide at least one setting or table change")
        added = {t.source_table_identifier for t in self.additional_tables or []}
        removed = {t.source_table_identifier for t in self.removed_tables or []}
        if added & removed:
            raise ValueError("A table cannot be added and removed in the same update")
        return self
