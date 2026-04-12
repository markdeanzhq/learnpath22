from pydantic import BaseModel, Field


class GraphNodeData(BaseModel):
    id: str
    label: str
    category: str | None = None
    group_id: str | None = None
    difficulty: int | None = None
    importance: int | None = None
    estimated_hours: float | None = None
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
