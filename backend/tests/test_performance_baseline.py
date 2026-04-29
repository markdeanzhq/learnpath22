"""Performance regression baselines for graph read APIs."""
from __future__ import annotations

import os
from statistics import mean
from time import perf_counter
from typing import Awaitable, Callable

import pytest


_REPEAT = int(os.getenv("PERF_BASELINE_REPEAT", "3"))
_WARMUP = int(os.getenv("PERF_BASELINE_WARMUP", "1"))


def _budget_ms(name: str, default: float) -> float:
    env_name = f"PERF_BUDGET_{name.upper()}_MS"
    return float(os.getenv(env_name, str(default)))


async def _measure_ms(call: Callable[[], Awaitable[object]]) -> list[float]:
    for _ in range(max(_WARMUP, 0)):
        response = await call()
        assert getattr(response, "status_code") == 200

    samples: list[float] = []
    for _ in range(max(_REPEAT, 1)):
        start = perf_counter()
        response = await call()
        samples.append((perf_counter() - start) * 1000)
        assert getattr(response, "status_code") == 200
    return samples


def _assert_budget(name: str, samples: list[float], budget_ms: float) -> None:
    worst_ms = max(samples)
    avg_ms = mean(samples)
    print(f"PERF_BASELINE {name}: avg={avg_ms:.2f}ms max={worst_ms:.2f}ms budget={budget_ms:.2f}ms")
    assert worst_ms <= budget_ms, (
        f"{name} exceeded performance budget: max={worst_ms:.2f}ms budget={budget_ms:.2f}ms "
        f"samples={[round(sample, 2) for sample in samples]}"
    )


@pytest.mark.parametrize(
    ("name", "path", "default_budget_ms"),
    [
        ("graph_path_latest", "/api/v1/projects/{project_id}/graph?scope=path&path_id=latest", 500.0),
        ("graph_domain", "/api/v1/projects/{project_id}/graph?scope=domain", 750.0),
        ("graph_project", "/api/v1/projects/{project_id}/graph?scope=project", 1000.0),
        ("graph_entities", "/api/v1/projects/{project_id}/graph/entities", 500.0),
        (
            "graph_workspace",
            "/api/v1/projects/{project_id}/graph/workspace?scope=path&path_id=latest&include_persisted_search_results=true",
            1200.0,
        ),
        (
            "graph_subgraph",
            "/api/v1/projects/{project_id}/graph/subgraph?node_ids=ml_c01,ml_a04,ml_c05",
            500.0,
        ),
    ],
)
async def test_graph_read_api_performance_baseline(client, project, name, path, default_budget_ms):
    endpoint = path.format(project_id=project["id"])
    samples = await _measure_ms(lambda: client.get(endpoint))
    _assert_budget(name, samples, _budget_ms(name, default_budget_ms))
