"""资源推荐与绑定 schemas"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class ResourceItem(BaseModel):
    id: str
    title: str
    url: str
    snippet: str | None = None
    score: float | None = None
    source_type: str
    stage_name: str | None = None
    node_id: str | None = None
    created_at: datetime | None = None


class StageResourceGroup(BaseModel):
    stage_name: str
    resources: list[ResourceItem]


class PlanResourcesResponse(BaseModel):
    path_id: str
    stages: list[StageResourceGroup]


class ManualResourceBindRequest(BaseModel):
    stage_name: str | None = None
    node_id: str | None = None
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    snippet: str | None = None

    @model_validator(mode="after")
    def validate_target(self) -> "ManualResourceBindRequest":
        if not self.stage_name and not self.node_id:
            raise ValueError("stage_name 和 node_id 至少提供一个")
        return self
