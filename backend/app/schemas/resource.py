"""资源推荐与绑定 schemas"""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator


class ResourceItem(BaseModel):
    id: str
    title: str
    url: str
    snippet: str | None = None
    score: float | None = None
    source_type: str
    stage_name: str | None = None
    node_id: str | None = None
    preference_match: str | None = None
    preference_reason: str | None = None
    created_at: datetime | None = None


class NodeResourceGroup(BaseModel):
    node_id: str
    node_name: str
    resources: list[ResourceItem] = Field(default_factory=list)


class StageResourceGroup(BaseModel):
    stage_name: str
    stage_resources: list[ResourceItem] = Field(default_factory=list)
    nodes: list[NodeResourceGroup] = Field(default_factory=list)


class PlanResourcesResponse(BaseModel):
    path_id: str
    stages: list[StageResourceGroup]


class ManualResourceBindRequest(BaseModel):
    stage_name: str | None = None
    node_id: str | None = None
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    snippet: str | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        normalized = value.strip()
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url 仅支持 http/https 链接")
        return normalized

    @model_validator(mode="after")
    def validate_target(self) -> "ManualResourceBindRequest":
        if not self.stage_name and not self.node_id:
            raise ValueError("stage_name 和 node_id 至少提供一个")
        return self
