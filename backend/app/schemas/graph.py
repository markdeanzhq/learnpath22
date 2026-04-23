from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class GraphNodeData(BaseModel):
    id: str
    label: str
    category: Optional[str] = None
    group_id: Optional[str] = None
    difficulty: Optional[int] = None
    importance: Optional[int] = None
    estimated_hours: Optional[float] = None
    is_main_path: bool = False


class GraphEdgeData(BaseModel):
    source: str
    target: str
    type: str
    reason: str = ""


class GraphElement(BaseModel):
    group: str = Field(description="'nodes' or 'edges'")
    data: dict


class GraphResponse(BaseModel):
    elements: list[GraphElement]


class SeedGraphResponse(BaseModel):
    nodes: int
    edges: int
    message: str = "Graph synced successfully"
