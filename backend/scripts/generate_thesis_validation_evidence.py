"""Generate structured thesis validation evidence from the fixed scenario matrix."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


class RequestJsonError(RuntimeError):
    def __init__(self, method: str, path: str, status_code: int):
        self.method = method
        self.path = path
        self.status_code = status_code
        super().__init__(f"{method} {path} -> HTTP {status_code}")


DEFAULT_BASE_URL = "http://127.0.0.1:8010/api/v1"
DEFAULT_MATRIX_FILE = Path(__file__).with_name("thesis_validation_matrix.json")
DEFAULT_OUTPUT_FILE = (
    Path(__file__).resolve().parents[1]
    / "artifacts"
    / "thesis_validation"
    / "latest.json"
)
DEFAULT_SUMMARY_FILE = (
    Path(__file__).resolve().parents[1]
    / "artifacts"
    / "thesis_validation"
    / "paper_metrics.json"
)
DEFAULT_REPORT_FILE = (
    Path(__file__).resolve().parents[1]
    / "artifacts"
    / "thesis_validation"
    / "report.md"
)
DEFAULT_REQUIRES_FILE = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "domain_packs"
    / "machine_learning"
    / "requires_edges.json"
)


async def request_json(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    expected: int = 200,
) -> Any:
    response = await client.request(method, path, json=payload)
    if response.status_code != expected:
        raise RequestJsonError(method, path, response.status_code)
    return response.json()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_matrix(matrix_file: Path) -> dict[str, Any]:
    return load_json(matrix_file)


def load_requires_edges(requires_file: Path) -> list[dict[str, Any]]:
    return load_json(requires_file)


def index_by_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in items}


def build_stage_summary(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "stage_index": stage.get("stage_index"),
            "stage_name": stage.get("stage_name"),
            "task_count": len(stage.get("tasks", [])),
            "estimated_hours": stage.get("estimated_hours", 0),
            "task_node_ids": [task.get("node_id") for task in stage.get("tasks", [])],
            "task_names": [task.get("name") for task in stage.get("tasks", [])],
        }
        for stage in stages
    ]


def build_explanation_counts(explanation: dict[str, Any]) -> dict[str, int]:
    return {
        "node_explanations": len(explanation.get("node_explanations", [])),
        "ordering_explanations": len(explanation.get("ordering_explanations", [])),
        "stage_explanations": len(explanation.get("stage_explanations", [])),
        "reinforcement_explanations": len(explanation.get("reinforcement_explanations", [])),
        "dependency_chain_explanations": len(
            explanation.get("dependency_chain_explanations", [])
        ),
    }


def build_checks(
    plan_response: dict[str, Any],
    latest_plan_response: dict[str, Any],
    explanation_counts: dict[str, int],
    tracking_evidence: dict[str, Any],
) -> dict[str, bool]:
    return {
        "plan_generated": plan_response.get("node_count", 0) > 0,
        "stage_plan_available": len(plan_response.get("stages", [])) > 0,
        "audit_available": bool(latest_plan_response.get("audit")),
        "explanations_available": explanation_counts["node_explanations"] > 0,
        **build_tracking_checks(tracking_evidence),
    }


def get_failed_checks(checks: dict[str, bool]) -> list[str]:
    return [check_name for check_name, passed in checks.items() if not passed]


def is_scenario_passed(result: dict[str, Any]) -> bool:
    return result.get("status") == "ok" and result.get("scenario_passed", True)


def get_scenario_report_status(result: dict[str, Any]) -> str:
    if result.get("status") == "error":
        return "error"
    return "ok" if is_scenario_passed(result) else "failed"


def resolve_search_execution(
    runtime_mode: str,
    search_query: str | None,
) -> tuple[bool, str | None]:
    if not search_query:
        return False, None
    if runtime_mode in {"offline", "hybrid"}:
        return False, f"search disabled by runtime_mode={runtime_mode}"
    return True, None


def resolve_execution_runtime_mode(
    requested_runtime_mode: str,
    readiness: dict[str, Any],
) -> str:
    if requested_runtime_mode != "auto":
        return requested_runtime_mode
    services = normalize_readiness(readiness).get("services", {})
    llm_ready = bool(services.get("llm", {}).get("ready"))
    search_ready = bool(services.get("search", {}).get("ready"))
    if llm_ready and search_ready:
        return "online"
    if search_ready:
        return "search"
    if llm_ready:
        return "hybrid"
    return "offline"


def should_trust_env_for_base_url(base_url: str) -> bool:
    host = httpx.URL(base_url).host or ""
    return not (host == "localhost" or host.startswith("127.") or host == "::1")


def utc_now_iso(value: datetime | None = None) -> str:
    moment = value or datetime.now(timezone.utc)
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_search_error_metadata(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, RequestJsonError):
        return {
            "kind": "http_error",
            "method": exc.method,
            "path": exc.path,
            "status_code": exc.status_code,
        }
    return {
        "kind": exc.__class__.__name__,
        "message": "search request failed",
    }


def build_preview_error_metadata(preview_response: Any) -> dict[str, Any]:
    payload = preview_response if isinstance(preview_response, dict) else {}
    missing_fields: list[str] = []
    if not payload.get("session_id"):
        missing_fields.append("session_id")
    recommended_candidate_id = payload.get("recommended_candidate_id")
    if not recommended_candidate_id:
        missing_fields.append("recommended_candidate_id")
    candidates = payload.get("candidates")
    candidate_count = len(candidates) if isinstance(candidates, list) else 0
    candidate_ids = {
        candidate.get("candidate_id")
        for candidate in candidates
        if isinstance(candidate, dict) and candidate.get("candidate_id")
    } if isinstance(candidates, list) else set()
    return {
        "kind": "invalid_preview_response",
        "missing_fields": missing_fields,
        "candidate_count": candidate_count,
        "recommended_candidate_missing": bool(
            recommended_candidate_id and candidate_count > 0 and recommended_candidate_id not in candidate_ids
        ),
    }


async def resolve_preview_response(
    client: httpx.AsyncClient,
    preview_response: dict[str, Any],
    *,
    goal_text: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    current = preview_response
    clarification_evidence: list[dict[str, Any]] = []
    max_turns = int(current.get("max_turns") or 5)

    while current.get("result_type") == "answer_clarification" and len(clarification_evidence) < max_turns:
        questions = current.get("questions") if isinstance(current.get("questions"), list) else []
        question = questions[0] if questions and isinstance(questions[0], dict) else {}
        session_id = str(current.get("clarification_session_id") or "")
        question_id = str(question.get("question_id") or "")
        if not session_id or not question_id:
            break

        answer_response = await request_json(
            client,
            "POST",
            f"/goal-resolution/clarifications/{session_id}/answers",
            payload={"answers": [{"question_id": question_id, "free_text": goal_text}]},
        )
        coverage_response = answer_response.get("coverage_response")
        clarification_evidence.append({
            "clarification_session_id": session_id,
            "question_id": question_id,
            "turn_count": answer_response.get("turn_count"),
            "status": answer_response.get("status"),
            "coverage_response_type": (
                coverage_response.get("result_type") if isinstance(coverage_response, dict) else None
            ),
        })
        if isinstance(coverage_response, dict):
            current = coverage_response
            break
        if answer_response.get("status") != "active":
            current = answer_response if isinstance(answer_response, dict) else current
            break
        current = {
            "result_type": "answer_clarification",
            "clarification_session_id": answer_response.get("clarification_session_id"),
            "questions": answer_response.get("questions", []),
            "turn_count": answer_response.get("turn_count"),
            "max_turns": answer_response.get("max_turns", max_turns),
        }
        max_turns = int(current.get("max_turns") or max_turns)

    return current, clarification_evidence


def ensure_readiness_service(
    service: dict[str, Any] | None,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(fallback)
    if isinstance(service, dict):
        normalized.update(service)
        if "reason" not in service and any(key in service for key in ("status", "ready")):
            normalized.pop("reason", None)
    return normalized


def normalize_readiness(readiness: dict[str, Any]) -> dict[str, Any]:
    services = readiness.get("services", {}) if isinstance(readiness, dict) else {}
    sqlite = ensure_readiness_service(
        services.get("sqlite") if isinstance(services, dict) else None,
        {"status": "error", "ready": False, "reason": "SQLite 状态缺失"},
    )
    neo4j = ensure_readiness_service(
        services.get("neo4j") if isinstance(services, dict) else None,
        {"status": "error", "ready": False, "reason": "Neo4j 状态缺失"},
    )
    llm = ensure_readiness_service(
        services.get("llm") if isinstance(services, dict) else None,
        {"status": "skipped", "ready": False, "reason": "LLM 状态缺失"},
    )
    search = ensure_readiness_service(
        services.get("search") if isinstance(services, dict) else None,
        {"status": "skipped", "ready": False, "reason": "搜索状态缺失", "provider": "tavily"},
    )
    graph_sync = ensure_readiness_service(
        services.get("graph_sync") if isinstance(services, dict) else None,
        {
            "status": "unknown" if sqlite.get("ready") and neo4j.get("ready") else "blocked",
            "ready": bool(sqlite.get("ready") and neo4j.get("ready")),
            "domain": "machine_learning",
            "reason": (
                "联调接口未单独返回图谱同步状态，当前按论文主链依赖兼容估算"
                if sqlite.get("ready") and neo4j.get("ready")
                else "联调接口未返回图谱同步状态，且论文主链基础依赖未全部就绪"
            ),
        },
    )
    core_ready = readiness.get("core_ready") if isinstance(readiness, dict) else None
    if core_ready is None:
        core_ready = bool(sqlite.get("ready") and neo4j.get("ready") and graph_sync.get("ready"))
    demo_ready = readiness.get("demo_ready") if isinstance(readiness, dict) else None
    if demo_ready is None:
        demo_ready = core_ready
    enhanced_ready = readiness.get("enhanced_ready") if isinstance(readiness, dict) else None
    if enhanced_ready is None:
        enhanced_ready = bool(llm.get("ready") and search.get("ready"))
    ready = bool(demo_ready and enhanced_ready)

    return {
        "status": "ready" if ready else "degraded",
        "ready": ready,
        "core_ready": bool(core_ready),
        "demo_ready": bool(demo_ready),
        "enhanced_ready": bool(enhanced_ready),
        "services": {
            "sqlite": sqlite,
            "neo4j": neo4j,
            "graph_sync": graph_sync,
            "llm": llm,
            "search": search,
        },
    }


def describe_readiness_payload(readiness: dict[str, Any]) -> dict[str, Any]:
    has_services_object = bool(
        isinstance(readiness, dict) and isinstance(readiness.get("services"), dict)
    )
    services = readiness.get("services", {}) if has_services_object else {}
    has_dual_layer_fields = bool(
        isinstance(readiness, dict)
        and all(key in readiness for key in ("core_ready", "demo_ready", "enhanced_ready"))
    )
    has_graph_sync = bool(isinstance(services, dict) and "graph_sync" in services)

    if has_dual_layer_fields and has_graph_sync:
        mode = "native_dual_layer"
        normalized = False
        reason = "health/readiness 已直接返回双层预检字段与 graph_sync"
    elif has_services_object:
        mode = "legacy_normalized"
        normalized = True
        reason = (
            "health/readiness 仍是旧结构，已通过 normalize_readiness 补齐 "
            "graph_sync/core_ready/demo_ready/enhanced_ready"
        )
    else:
        mode = "unavailable"
        normalized = False
        reason = "readiness payload unavailable"

    return {
        "mode": mode,
        "normalized": normalized,
        "has_dual_layer_fields": has_dual_layer_fields,
        "has_graph_sync": has_graph_sync,
        "target_schema": "dual_layer_readiness_v1",
        "target_fields": [
            "status",
            "ready",
            "core_ready",
            "demo_ready",
            "enhanced_ready",
            "services.graph_sync",
        ],
        "reason": reason,
    }


def build_validation_contract(readiness_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "readiness_contract": readiness_payload,
        "tracking_contract": {
            "summary_scope": "latest_plan",
            "verified_checks": [
                "tracking_summary_matches_initial_plan",
                "tracking_summary_matches_progress_latest_plan",
                "tracking_summary_matches_profile_latest_plan",
            ],
        },
    }


def extract_plan_node_ids(plan_payload: dict[str, Any]) -> list[str]:
    return [
        task["node_id"]
        for stage in plan_payload.get("stages", [])
        for task in stage.get("tasks", [])
        if task.get("node_id")
    ]


def build_tracking_summary_expected(
    plan_payload: dict[str, Any],
    *,
    completed_ids: tuple[str, ...] = (),
    in_progress_ids: tuple[str, ...] = (),
    skipped_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    plan_ids = set(extract_plan_node_ids(plan_payload))
    completed = len(plan_ids & set(completed_ids))
    in_progress = len(plan_ids & set(in_progress_ids))
    skipped = len(plan_ids & set(skipped_ids))
    total = len(plan_ids)
    pending = total - completed - in_progress - skipped
    completion_rate = round(completed / total, 3) if total else 0.0
    return {
        "total_nodes": total,
        "completed": completed,
        "in_progress": in_progress,
        "skipped": skipped,
        "pending": pending,
        "completion_rate": completion_rate,
    }


def choose_safe_skipped_node_id(
    *,
    node_ids: list[str],
    goal_result: dict[str, Any],
    audit: dict[str, Any],
) -> str | None:
    confirmed_target_ids = set(goal_result.get("confirmed_target_node_ids") or goal_result.get("target_node_ids") or [])
    closure_ids = set(audit.get("closure_ids") or [])
    protected_ids = confirmed_target_ids | closure_ids
    for node_id in node_ids:
        if node_id not in protected_ids:
            return node_id
    return None


def choose_safe_removed_node_id(
    *,
    pending_node_ids: list[str],
    goal_result: dict[str, Any],
) -> str | None:
    confirmed_target_ids = set(goal_result.get("confirmed_target_node_ids") or goal_result.get("target_node_ids") or [])
    for node_id in pending_node_ids:
        if node_id not in confirmed_target_ids:
            return node_id
    return None


async def add_tracking_event(
    client: httpx.AsyncClient,
    project_id: str,
    node_id: str,
    event_type: str,
    note: str,
) -> dict[str, Any]:
    return await request_json(
        client,
        "POST",
        f"/projects/{project_id}/tracking/events",
        payload={
            "node_id": node_id,
            "event_type": event_type,
            "note": note,
        },
    )


async def collect_tracking_evidence(
    client: httpx.AsyncClient,
    project_id: str,
    latest_plan_response: dict[str, Any],
) -> dict[str, Any]:
    node_ids = extract_plan_node_ids(latest_plan_response)
    goal_result = latest_plan_response.get("audit", {}).get("goal_result", {})
    audit = latest_plan_response.get("audit", {})

    completed_node_id = node_ids[0] if node_ids else None
    in_progress_node_id = node_ids[1] if len(node_ids) > 1 else None
    skipped_node_id = choose_safe_skipped_node_id(
        node_ids=node_ids[2:] if len(node_ids) > 2 else [],
        goal_result=goal_result,
        audit=audit,
    )

    if completed_node_id:
        await add_tracking_event(client, project_id, completed_node_id, "complete", "论文验证：完成首个节点")
    if in_progress_node_id:
        await add_tracking_event(client, project_id, in_progress_node_id, "start", "论文验证：开始第二个节点")
    if skipped_node_id:
        await add_tracking_event(client, project_id, skipped_node_id, "skip", "论文验证：跳过安全节点")

    tracked_completed_ids = tuple(node_id for node_id in (completed_node_id,) if node_id)
    tracked_in_progress_ids = tuple(node_id for node_id in (in_progress_node_id,) if node_id)
    tracked_skipped_ids = tuple(node_id for node_id in (skipped_node_id,) if node_id)

    initial_summary = await request_json(client, "GET", f"/projects/{project_id}/tracking/summary")
    initial_expected = build_tracking_summary_expected(
        latest_plan_response,
        completed_ids=tracked_completed_ids,
        in_progress_ids=tracked_in_progress_ids,
        skipped_ids=tracked_skipped_ids,
    )

    progress_aware_replan = await request_json(
        client,
        "POST",
        f"/projects/{project_id}/replans",
        payload={"mode": "progress_aware", "reason": "论文验证：latest 计划口径检查"},
    )
    latest_progress_plan = await request_json(client, "GET", f"/projects/{project_id}/plans/latest")
    progress_summary = await request_json(client, "GET", f"/projects/{project_id}/tracking/summary")
    progress_expected = build_tracking_summary_expected(
        latest_progress_plan,
        completed_ids=tracked_completed_ids,
        in_progress_ids=tracked_in_progress_ids,
        skipped_ids=tracked_skipped_ids,
    )

    profile_update: dict[str, Any] = {
        "skipped": True,
        "reason": "progress_aware 重规划后无可安全移除待规划节点",
    }
    pending_node_ids = progress_aware_replan.get("diff", {}).get("pending", [])
    removed_node_id = choose_safe_removed_node_id(
        pending_node_ids=pending_node_ids,
        goal_result=latest_progress_plan.get("audit", {}).get("goal_result", {}),
    )
    if removed_node_id:
        await request_json(
            client,
            "PATCH",
            f"/projects/{project_id}/graph/nodes/{removed_node_id}",
            payload={"status": "removed"},
        )
        profile_update_replan = await request_json(
            client,
            "POST",
            f"/projects/{project_id}/replans",
            payload={"mode": "profile_update", "reason": "论文验证：latest 计划重规划口径检查"},
        )
        latest_profile_plan = await request_json(client, "GET", f"/projects/{project_id}/plans/latest")
        profile_summary = await request_json(client, "GET", f"/projects/{project_id}/tracking/summary")
        profile_expected = build_tracking_summary_expected(
            latest_profile_plan,
            completed_ids=tracked_completed_ids,
            in_progress_ids=tracked_in_progress_ids,
            skipped_ids=tracked_skipped_ids,
        )
        profile_update = {
            "skipped": False,
            "removed_node_id": removed_node_id,
            "replan_response": profile_update_replan,
            "latest_plan_version": latest_profile_plan.get("version"),
            "latest_plan_node_count": len(extract_plan_node_ids(latest_profile_plan)),
            "removed_node_retained": removed_node_id in set(extract_plan_node_ids(latest_profile_plan)),
            "summary": profile_summary,
            "expected_summary": profile_expected,
            "matches_latest_plan": profile_summary == profile_expected,
        }

    return {
        "sample_nodes": {
            "completed_node_id": completed_node_id,
            "in_progress_node_id": in_progress_node_id,
            "skipped_node_id": skipped_node_id,
        },
        "initial_summary": {
            "summary": initial_summary,
            "expected_summary": initial_expected,
            "matches_plan": initial_summary == initial_expected,
        },
        "progress_aware": {
            "replan_response": progress_aware_replan,
            "latest_plan_version": latest_progress_plan.get("version"),
            "latest_plan_node_count": len(extract_plan_node_ids(latest_progress_plan)),
            "completed_node_retained": bool(
                completed_node_id and completed_node_id in set(extract_plan_node_ids(latest_progress_plan))
            ),
            "summary": progress_summary,
            "expected_summary": progress_expected,
            "matches_latest_plan": progress_summary == progress_expected,
        },
        "profile_update": profile_update,
    }


def build_tracking_checks(tracking_evidence: dict[str, Any]) -> dict[str, bool]:
    profile_update = tracking_evidence.get("profile_update", {})
    profile_matches = profile_update.get("matches_latest_plan", False)
    if profile_update.get("skipped"):
        profile_matches = True
    elif profile_update.get("removed_node_retained"):
        profile_matches = False
    return {
        "tracking_summary_matches_initial_plan": tracking_evidence.get("initial_summary", {}).get("matches_plan", False),
        "tracking_summary_matches_progress_latest_plan": tracking_evidence.get("progress_aware", {}).get("matches_latest_plan", False),
        "tracking_summary_matches_profile_latest_plan": profile_matches,
    }


def get_actual_online_dependency_usage(results: list[dict[str, Any]]) -> dict[str, bool]:
    llm_used = False
    search_used = False

    for result in results:
        goal_result = result.get("latest_plan_response", {}).get("audit", {}).get("goal_result", {})
        source_breakdown = goal_result.get("source_breakdown") or {}
        llm_contribution = source_breakdown.get("llm", 0)
        if goal_result.get("resolve_source") == "llm" or llm_contribution > 0:
            llm_used = True

        collector_source = result.get("collector_questions_response", {}).get("source")
        if collector_source == "llm":
            llm_used = True

        if result.get("search_attempted"):
            search_used = True

    return {
        "llm": llm_used,
        "search": search_used,
    }


def resolve_runtime_mode(actual_usage: dict[str, bool]) -> str:
    if actual_usage["llm"] and actual_usage["search"]:
        return "online"
    if actual_usage["search"]:
        return "search"
    if actual_usage["llm"]:
        return "hybrid"
    return "offline"


def build_dependency_metadata(
    health: dict[str, Any],
    readiness: dict[str, Any],
    actual_usage: dict[str, bool],
) -> dict[str, Any]:
    environment = health.get("environment", {}) if isinstance(health, dict) else {}
    normalized_readiness = normalize_readiness(readiness)
    services = normalized_readiness.get("services", {})
    llm_service = services.get("llm", {})
    search_service = services.get("search", {})
    graph_sync_service = services.get("graph_sync", {})

    return {
        "llm": {
            "configured": bool(environment.get("llm_api_key_set")),
            "used_in_run": actual_usage["llm"],
            "provider": environment.get("llm_provider"),
            "status": llm_service.get("status"),
            "ready": llm_service.get("ready"),
            "reason": llm_service.get("reason"),
            "base_url": llm_service.get("base_url"),
            "model": llm_service.get("model"),
        },
        "search": {
            "configured": bool(environment.get("search_api_key_set")),
            "used_in_run": actual_usage["search"],
            "provider": search_service.get("provider") or environment.get("search_provider"),
            "status": search_service.get("status"),
            "ready": search_service.get("ready"),
            "reason": search_service.get("reason"),
        },
        "graph_sync": {
            "status": graph_sync_service.get("status"),
            "ready": graph_sync_service.get("ready"),
            "reason": graph_sync_service.get("reason"),
            "domain": graph_sync_service.get("domain"),
            "version": graph_sync_service.get("version"),
            "pack_hash": graph_sync_service.get("pack_hash"),
            "main_graph_synced": graph_sync_service.get("main_graph_synced"),
            "entity_graph_synced": graph_sync_service.get("entity_graph_synced"),
            "nodes": graph_sync_service.get("nodes"),
            "edges": graph_sync_service.get("edges"),
        },
    }


def build_run_metadata(
    *,
    requested_runtime_mode: str,
    started_at: datetime,
    finished_at: datetime,
    health: dict[str, Any],
    readiness: dict[str, Any],
    actual_usage: dict[str, bool],
) -> dict[str, Any]:
    resolved_runtime_mode = resolve_runtime_mode(actual_usage)
    normalized_readiness = normalize_readiness(readiness)
    readiness_contract = describe_readiness_payload(readiness)

    return {
        "started_at_utc": utc_now_iso(started_at),
        "finished_at_utc": utc_now_iso(finished_at),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "requested_runtime_mode": requested_runtime_mode,
        "resolved_runtime_mode": resolved_runtime_mode,
        "uses_online_dependencies": any(actual_usage.values()),
        "readiness_status": normalized_readiness.get("status"),
        "readiness_ready": normalized_readiness.get("ready"),
        "core_ready": normalized_readiness.get("core_ready"),
        "demo_ready": normalized_readiness.get("demo_ready"),
        "enhanced_ready": normalized_readiness.get("enhanced_ready"),
        "readiness_contract": readiness_contract,
        "dependency_metadata": build_dependency_metadata(health, normalized_readiness, actual_usage),
    }


def build_requires_lookup(requires_edges: list[dict[str, Any]]) -> dict[str, set[str]]:
    lookup: dict[str, set[str]] = {}
    for edge in requires_edges:
        target = edge.get("target")
        source = edge.get("source")
        if not target or not source:
            continue
        lookup.setdefault(target, set()).add(source)
    return lookup


def compute_dependency_metrics(
    results: list[dict[str, Any]],
    requires_lookup: dict[str, set[str]],
) -> dict[str, Any]:
    total_required_edges = 0
    satisfied_required_edges = 0
    scenario_summaries: list[dict[str, Any]] = []

    for result in results:
        if result.get("status") == "error":
            scenario_summaries.append(
                {
                    "scenario_id": result.get("scenario_id"),
                    "status": get_scenario_report_status(result),
                    "satisfied_required_edges": 0,
                    "total_required_edges": 0,
                    "dependency_satisfaction_ratio": 0.0,
                }
            )
            continue

        ordered_node_ids = [
            task.get("node_id")
            for stage in result.get("plan_response", {}).get("stages", [])
            for task in stage.get("tasks", [])
            if task.get("node_id")
        ]
        order_map = {node_id: index for index, node_id in enumerate(ordered_node_ids)}

        scenario_total = 0
        scenario_satisfied = 0
        for node_id in ordered_node_ids:
            for prerequisite_id in requires_lookup.get(node_id, set()):
                scenario_total += 1
                prerequisite_order = order_map.get(prerequisite_id)
                if prerequisite_order is not None and prerequisite_order < order_map[node_id]:
                    scenario_satisfied += 1

        total_required_edges += scenario_total
        satisfied_required_edges += scenario_satisfied
        ratio = round(scenario_satisfied / scenario_total, 4) if scenario_total else 1.0
        scenario_summaries.append(
            {
                "scenario_id": result.get("scenario_id"),
                "status": get_scenario_report_status(result),
                "satisfied_required_edges": scenario_satisfied,
                "total_required_edges": scenario_total,
                "dependency_satisfaction_ratio": ratio,
            }
        )

    overall_ratio = (
        round(satisfied_required_edges / total_required_edges, 4)
        if total_required_edges
        else 1.0
    )

    return {
        "satisfied_required_edges": satisfied_required_edges,
        "total_required_edges": total_required_edges,
        "dependency_satisfaction_ratio": overall_ratio,
        "scenario_breakdown": scenario_summaries,
    }


def compute_stage_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    stage_count_values: list[int] = []
    stage_hours_values: list[float] = []
    per_scenario: list[dict[str, Any]] = []

    for result in results:
        if result.get("status") == "error":
            per_scenario.append(
                {
                    "scenario_id": result.get("scenario_id"),
                    "status": get_scenario_report_status(result),
                    "stage_count": 0,
                    "total_stage_hours": 0,
                    "stages": [],
                }
            )
            continue

        stage_summary = result.get("stage_summary", [])
        stage_count = len(stage_summary)
        total_stage_hours = round(
            sum(stage.get("estimated_hours", 0) for stage in stage_summary),
            1,
        )
        stage_count_values.append(stage_count)
        stage_hours_values.append(total_stage_hours)
        per_scenario.append(
            {
                "scenario_id": result.get("scenario_id"),
                "status": get_scenario_report_status(result),
                "stage_count": stage_count,
                "total_stage_hours": total_stage_hours,
                "stages": [
                    {
                        "stage_name": stage.get("stage_name"),
                        "task_count": stage.get("task_count", 0),
                        "estimated_hours": stage.get("estimated_hours", 0),
                    }
                    for stage in stage_summary
                ],
            }
        )

    return {
        "scenario_breakdown": per_scenario,
        "average_stage_count": round(sum(stage_count_values) / len(stage_count_values), 2)
        if stage_count_values
        else 0.0,
        "average_total_stage_hours": round(sum(stage_hours_values) / len(stage_hours_values), 2)
        if stage_hours_values
        else 0.0,
        "min_stage_count": min(stage_count_values) if stage_count_values else 0,
        "max_stage_count": max(stage_count_values) if stage_count_values else 0,
    }


def compute_environment_metrics(
    health: dict[str, Any],
    readiness: dict[str, Any],
    run_metadata: dict[str, Any],
) -> dict[str, Any]:
    environment = health.get("environment", {}) if isinstance(health, dict) else {}
    normalized_readiness = normalize_readiness(readiness)
    services = normalized_readiness.get("services", {})
    readiness_contract = run_metadata.get("readiness_contract", {})

    service_statuses = {
        service_name: {
            "status": service.get("status"),
            "ready": service.get("ready"),
            "reason": service.get("reason"),
        }
        for service_name, service in services.items()
    }

    return {
        "prototype_scope": environment.get("prototype_scope"),
        "delivery_stage": environment.get("delivery_stage"),
        "python_baseline": environment.get("python_baseline"),
        "python_version": environment.get("python_version"),
        "runtime_settings_scope": environment.get("runtime_settings_scope"),
        "readiness_status": run_metadata.get("readiness_status"),
        "readiness_ready": run_metadata.get("readiness_ready"),
        "core_ready": run_metadata.get("core_ready"),
        "demo_ready": run_metadata.get("demo_ready"),
        "enhanced_ready": run_metadata.get("enhanced_ready"),
        "readiness_contract_mode": readiness_contract.get("mode"),
        "readiness_contract_normalized": readiness_contract.get("normalized"),
        "tracking_summary_scope": "latest_plan",
        "resolved_runtime_mode": run_metadata.get("resolved_runtime_mode"),
        "uses_online_dependencies": run_metadata.get("uses_online_dependencies"),
        "service_statuses": service_statuses,
    }


def format_bool(value: Any) -> str:
    return "是" if bool(value) else "否"


def format_percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def markdown_cell(value: Any) -> str:
    text = str(value) if value is not None else "-"
    return text.replace("|", "\\|").replace("\n", " ")


def build_markdown_header(context: dict[str, Any]) -> list[str]:
    evidence = context["evidence"]
    paper_metrics = context["paper_metrics"]
    run_metadata = context["run_metadata"]
    generated_at = run_metadata.get("finished_at_utc") or run_metadata.get("started_at_utc") or "-"
    return [
        "# LearnPath-KG 论文验证自动评估报告",
        "",
        f"- 生成时间：{generated_at}",
        f"- Matrix：`{evidence.get('matrix_id', '-')}`",
        f"- Change：`{evidence.get('change', '-')}`",
        f"- 引用就绪：{format_bool(paper_metrics.get('citation_ready'))}",
        "",
    ]


def build_markdown_conclusion(summary: dict[str, Any], stage_evidence: dict[str, Any]) -> list[str]:
    return [
        "## 1. 总体验证结论",
        "",
        f"- 场景通过：{summary.get('successful_scenarios', 0)}/{summary.get('scenario_count', 0)}",
        f"- 全部场景通过：{format_bool(summary.get('all_scenarios_passed'))}",
        f"- 依赖满足率：{format_percent(summary.get('dependency_satisfaction_ratio'))}",
        f"- 平均阶段数：{stage_evidence.get('average_stage_count', 0)}",
        f"- 平均阶段总时长：{stage_evidence.get('average_total_stage_hours', 0)} 小时",
        "",
    ]


def build_markdown_environment(environment: dict[str, Any], run_metadata: dict[str, Any]) -> list[str]:
    runtime_mode = environment.get("resolved_runtime_mode") or run_metadata.get("resolved_runtime_mode") or "-"
    readiness = environment.get("readiness_status") or run_metadata.get("readiness_status") or "-"
    return [
        "## 2. 运行环境与依赖状态",
        "",
        f"- 运行模式：`{runtime_mode}`",
        f"- 使用在线依赖：{format_bool(environment.get('uses_online_dependencies'))}",
        f"- Readiness：`{readiness}`",
        f"- Core ready：{format_bool(environment.get('core_ready'))}",
        f"- Demo ready：{format_bool(environment.get('demo_ready'))}",
        f"- Enhanced ready：{format_bool(environment.get('enhanced_ready'))}",
        f"- Tracking 统计口径：`{environment.get('tracking_summary_scope', 'latest_plan')}`",
        "",
    ]


def build_markdown_scenario_table(
    results: list[Any],
    dependency_by_scenario: dict[Any, dict[str, Any]],
) -> list[str]:
    lines = [
        "## 3. 场景明细",
        "",
        "| 场景 ID | 标题 | 状态 | 节点数 | 阶段数 | 总时长 | 依赖满足率 | 失败检查 |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for result in results:
        if isinstance(result, dict):
            lines.append(build_markdown_scenario_row(result, dependency_by_scenario))
    return lines + [""]


def build_markdown_scenario_row(
    result: dict[str, Any],
    dependency_by_scenario: dict[Any, dict[str, Any]],
) -> str:
    scenario_id = result.get("scenario_id")
    plan_response = result.get("plan_response", {}) if isinstance(result.get("plan_response"), dict) else {}
    stage_summary = result.get("stage_summary", []) if isinstance(result.get("stage_summary"), list) else []
    dependency_summary = dependency_by_scenario.get(scenario_id, {})
    total_hours = round(sum(stage.get("estimated_hours", 0) for stage in stage_summary), 1)
    failed_checks = ", ".join(result.get("failed_checks") or []) or "-"
    cells = [
        scenario_id,
        result.get("scenario_title"),
        get_scenario_report_status(result),
        plan_response.get("node_count", len(extract_plan_node_ids(plan_response))),
        len(stage_summary),
        total_hours,
        format_percent(dependency_summary.get("dependency_satisfaction_ratio")),
        failed_checks,
    ]
    return "| " + " | ".join(markdown_cell(cell) for cell in cells) + " |"


def build_markdown_evidence_boundary() -> list[str]:
    return [
        "## 4. 可引用证据边界",
        "",
        "- 本报告由固定场景矩阵通过 API 自动生成，原始证据保存在 `latest.json`。",
        "- `paper_metrics.json` 保留论文可引用的结构化指标，Markdown 报告只做可读化汇总。",
        "- 依赖正确性以 Domain Pack 的 `REQUIRES` 边为基准，检查路径内前置节点是否早于目标节点出现。",
        "- 路径正确性仍由知识图谱、项目快照、拓扑排序和规则评分保证，LLM/搜索只作为增强证据记录。",
        "",
    ]


def build_markdown_report(evidence: dict[str, Any], paper_metrics: dict[str, Any]) -> str:
    run_metadata = evidence.get("run_metadata", {}) if isinstance(evidence, dict) else {}
    summary = evidence.get("summary", {}) if isinstance(evidence, dict) else {}
    results = evidence.get("results", []) if isinstance(evidence, dict) else []
    dependency = paper_metrics.get("dependency_correctness", {}) if isinstance(paper_metrics, dict) else {}
    stage_evidence = paper_metrics.get("stage_evidence", {}) if isinstance(paper_metrics, dict) else {}
    environment = paper_metrics.get("environment_state", {}) if isinstance(paper_metrics, dict) else {}
    dependency_by_scenario = {
        item.get("scenario_id"): item
        for item in dependency.get("scenario_breakdown", [])
        if isinstance(item, dict)
    }
    sections = [
        *build_markdown_header({
            "evidence": evidence,
            "paper_metrics": paper_metrics,
            "run_metadata": run_metadata,
        }),
        *build_markdown_conclusion(summary, stage_evidence),
        *build_markdown_environment(environment, run_metadata),
        *build_markdown_scenario_table(results, dependency_by_scenario),
        *build_markdown_evidence_boundary(),
    ]
    return "\n".join(sections)


def build_summary(
    results: list[dict[str, Any]],
    context_errors: list[str],
    requires_lookup: dict[str, set[str]],
) -> dict[str, Any]:
    successful_scenarios = sum(1 for item in results if is_scenario_passed(item))
    failed_scenarios = len(results) - successful_scenarios
    dependency_metrics = compute_dependency_metrics(results, requires_lookup)

    return {
        "scenario_count": len(results),
        "successful_scenarios": successful_scenarios,
        "failed_scenarios": failed_scenarios,
        "context_errors": context_errors,
        "all_scenarios_passed": failed_scenarios == 0 and not context_errors,
        "satisfied_required_edges": dependency_metrics["satisfied_required_edges"],
        "total_required_edges": dependency_metrics["total_required_edges"],
        "dependency_satisfaction_ratio": dependency_metrics["dependency_satisfaction_ratio"],
    }


def build_paper_metrics(
    *,
    matrix: dict[str, Any],
    health: dict[str, Any],
    readiness: dict[str, Any],
    run_metadata: dict[str, Any],
    results: list[dict[str, Any]],
    summary: dict[str, Any],
    requires_lookup: dict[str, set[str]],
) -> dict[str, Any]:
    return {
        "matrix_id": matrix.get("matrix_id"),
        "change": matrix.get("change"),
        "citation_ready": bool(summary.get("all_scenarios_passed")),
        "scenario_overview": {
            "goal_template_count": len(matrix.get("goal_templates", [])),
            "profile_template_count": len(matrix.get("profile_templates", [])),
            "scenario_count": summary.get("scenario_count", 0),
            "successful_scenarios": summary.get("successful_scenarios", 0),
            "failed_scenarios": summary.get("failed_scenarios", 0),
        },
        "dependency_correctness": compute_dependency_metrics(results, requires_lookup),
        "stage_evidence": compute_stage_metrics(results),
        "environment_state": compute_environment_metrics(health, readiness, run_metadata),
    }


async def capture_context(client: httpx.AsyncClient) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[str]]:
    errors: list[str] = []

    try:
        health = await request_json(client, "GET", "/health")
    except Exception as exc:
        health = {"status": "error", "error": str(exc)}
        errors.append("health")

    try:
        raw_readiness = await request_json(client, "GET", "/health/readiness")
        readiness = normalize_readiness(raw_readiness)
    except Exception as exc:
        raw_readiness = {"status": "error", "error": str(exc)}
        readiness = raw_readiness
        errors.append("readiness")

    return health, raw_readiness, readiness, errors


async def run_scenario(
    client: httpx.AsyncClient,
    scenario: dict[str, Any],
    goals_by_id: dict[str, dict[str, Any]],
    profiles_by_id: dict[str, dict[str, Any]],
    runtime_mode: str = "auto",
) -> dict[str, Any]:
    goal = goals_by_id[scenario["goal_id"]]
    profile = profiles_by_id[scenario["profile_id"]]

    result: dict[str, Any] = {
        "scenario_id": scenario["id"],
        "scenario_title": scenario["title"],
        "goal": goal,
        "profile": profile,
    }
    search_attempted = False
    search_results: list[dict[str, Any]] = []
    search_error: dict[str, Any] | None = None
    search_skipped_reason: str | None = None

    try:
        project_payload = dict(goal["project"])
        requested_goal_type = project_payload.pop("goal_type", None)
        preview_response = await request_json(
            client,
            "POST",
            "/goal-resolution/preview",
            payload={
                "goal_text": project_payload["goal_text"],
                "requested_goal_type": requested_goal_type,
                "domain": project_payload.get("domain", "machine_learning"),
            },
        )
        preview_response, clarification_evidence = await resolve_preview_response(
            client,
            preview_response,
            goal_text=project_payload["goal_text"],
        )
        if clarification_evidence:
            result["clarification_evidence"] = clarification_evidence
        preview_error = build_preview_error_metadata(preview_response)
        if (
            preview_error["missing_fields"]
            or preview_error["candidate_count"] == 0
            or preview_error["recommended_candidate_missing"]
        ):
            result["preview_error"] = preview_error
            raise RuntimeError("invalid preview response")
        project_response = await request_json(
            client,
            "POST",
            "/projects",
            payload={
                "title": project_payload["title"],
                "goal_text": project_payload["goal_text"],
                "domain": project_payload.get("domain", "machine_learning"),
                "resolution_session_id": preview_response["session_id"],
                "selected_candidate_id": preview_response["recommended_candidate_id"],
            },
        )
        project_id = project_response["id"]
        result.update(
            {
                "project_id": project_id,
                "project_response": project_response,
            }
        )
        collector_questions_response = await request_json(
            client,
            "POST",
            f"/projects/{project_id}/collector/questions",
        )
        result["collector_questions_response"] = collector_questions_response
        search_query = goal.get("project", {}).get("goal_text")
        should_attempt_search, search_skipped_reason = resolve_search_execution(
            runtime_mode,
            search_query,
        )
        if should_attempt_search:
            search_attempted = True
            try:
                search_payload = await request_json(
                    client,
                    "POST",
                    f"/projects/{project_id}/search",
                    payload={"query": search_query, "max_results": 3},
                )
                search_results = search_payload.get("results", [])
            except Exception as exc:
                search_error = build_search_error_metadata(exc)
                raise RuntimeError("search failed") from exc
        profile_response = await request_json(
            client,
            "POST",
            f"/projects/{project_id}/profiles",
            payload=profile["profile"],
        )
        plan_response = await request_json(
            client,
            "POST",
            f"/projects/{project_id}/plans",
        )
        latest_plan_response = await request_json(
            client,
            "GET",
            f"/projects/{project_id}/plans/latest",
        )
        explanation_response = await request_json(
            client,
            "GET",
            f"/projects/{project_id}/explanation",
        )

        explanation_counts = build_explanation_counts(explanation_response)
        tracking_evidence = await collect_tracking_evidence(client, project_id, latest_plan_response)
        checks = build_checks(plan_response, latest_plan_response, explanation_counts, tracking_evidence)
        failed_checks = get_failed_checks(checks)
        scenario_passed = not failed_checks

        result.update(
            {
                "status": "ok",
                "scenario_passed": scenario_passed,
                "project_id": project_id,
                "profile_record_id": profile_response.get("id"),
                "collector_questions_response": collector_questions_response,
                "profile_response": profile_response,
                "plan_response": plan_response,
                "latest_plan_response": latest_plan_response,
                "search_attempted": search_attempted,
                "search_results": search_results,
                "search_skipped_reason": search_skipped_reason,
                "stage_summary": build_stage_summary(plan_response.get("stages", [])),
                "explanation_counts": explanation_counts,
                "explanation_response": explanation_response,
                "tracking_evidence": tracking_evidence,
                "checks": checks,
                "failed_checks": failed_checks,
            }
        )
        if failed_checks:
            result["error"] = f"critical checks failed: {', '.join(failed_checks)}"
    except Exception as exc:
        result.update(
            {
                "status": "error",
                "error": str(exc),
                "search_attempted": search_attempted,
                "search_results": search_results,
                "search_error": search_error,
                "search_skipped_reason": search_skipped_reason,
            }
        )

    return result


async def generate_evidence(
    base_url: str,
    matrix_file: Path,
    output_file: Path,
    summary_file: Path,
    runtime_mode: str,
    requires_file: Path,
    report_file: Path | None = None,
) -> int:
    started_at = datetime.now(timezone.utc)
    matrix = load_matrix(matrix_file)
    requires_lookup = build_requires_lookup(load_requires_edges(requires_file))
    goals_by_id = index_by_id(matrix["goal_templates"])
    profiles_by_id = index_by_id(matrix["profile_templates"])

    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=30.0,
        trust_env=should_trust_env_for_base_url(base_url),
    ) as client:
        health, raw_readiness, readiness, context_errors = await capture_context(client)
        execution_runtime_mode = resolve_execution_runtime_mode(runtime_mode, readiness)

        results: list[dict[str, Any]] = []
        for scenario in matrix["scenarios"]:
            print(f"▶ {scenario['id']} - {scenario['title']}")
            result = await run_scenario(
                client,
                scenario,
                goals_by_id,
                profiles_by_id,
                runtime_mode=execution_runtime_mode,
            )
            results.append(result)
            if result["status"] == "ok":
                print(f"  ✓ project={result['project_id']} nodes={result['plan_response'].get('node_count', 0)}")
            else:
                print(f"  ✗ {result['error']}")

    finished_at = datetime.now(timezone.utc)
    summary = build_summary(results, context_errors, requires_lookup)
    actual_usage = get_actual_online_dependency_usage(results)
    run_metadata = build_run_metadata(
        requested_runtime_mode=runtime_mode,
        started_at=started_at,
        finished_at=finished_at,
        health=health,
        readiness=raw_readiness,
        actual_usage=actual_usage,
    )

    evidence = {
        "matrix_id": matrix["matrix_id"],
        "change": matrix.get("change"),
        "description": matrix.get("description"),
        "matrix_file": str(matrix_file),
        "base_url": base_url,
        "run_metadata": run_metadata,
        "validation_contract": build_validation_contract(run_metadata["readiness_contract"]),
        "health": health,
        "readiness": readiness,
        "summary": summary,
        "results": results,
    }
    paper_metrics = build_paper_metrics(
        matrix=matrix,
        health=health,
        readiness=readiness,
        run_metadata=run_metadata,
        results=results,
        summary=summary,
        requires_lookup=requires_lookup,
    )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(
        json.dumps(paper_metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if report_file is not None:
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(
            build_markdown_report(evidence, paper_metrics),
            encoding="utf-8",
        )

    print(f"\nEvidence written to: {output_file}")
    print(f"Paper metrics written to: {summary_file}")
    if report_file is not None:
        print(f"Markdown report written to: {report_file}")
    print(
        "Summary: "
        f"{summary['successful_scenarios']}/{len(results)} scenarios passed"
        + ("" if not context_errors else f", context errors={','.join(context_errors)}")
    )

    return 0 if summary["all_scenarios_passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate thesis validation evidence from the fixed scenario matrix."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL")
    parser.add_argument(
        "--matrix-file",
        default=str(DEFAULT_MATRIX_FILE),
        help="Path to thesis validation matrix JSON",
    )
    parser.add_argument(
        "--output-file",
        default=str(DEFAULT_OUTPUT_FILE),
        help="Path to evidence output JSON",
    )
    parser.add_argument(
        "--runtime-mode",
        default="auto",
        choices=["auto", "online", "search", "hybrid", "offline"],
        help="Runtime mode label stored in evidence metadata",
    )
    parser.add_argument(
        "--summary-file",
        default=str(DEFAULT_SUMMARY_FILE),
        help="Path to paper metrics JSON",
    )
    parser.add_argument(
        "--report-file",
        default=str(DEFAULT_REPORT_FILE),
        help="Path to Markdown report output",
    )
    parser.add_argument(
        "--requires-file",
        default=str(DEFAULT_REQUIRES_FILE),
        help="Path to requires_edges.json used for dependency correctness metrics",
    )
    args = parser.parse_args()

    exit_code = asyncio.run(
        generate_evidence(
            base_url=args.base_url,
            matrix_file=Path(args.matrix_file),
            output_file=Path(args.output_file),
            summary_file=Path(args.summary_file),
            runtime_mode=args.runtime_mode,
            requires_file=Path(args.requires_file),
            report_file=Path(args.report_file) if args.report_file else None,
        )
    )
    sys.exit(exit_code)
