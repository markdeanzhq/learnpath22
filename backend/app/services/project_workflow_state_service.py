"""Project workflow state aggregation service."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.sqlite_models import LearnerProfile
from app.repositories.plan_repository import extract_plan_node_ids, get_latest_plan
from app.repositories.project_repository import get_project
from app.repositories.tracking_repository import get_events
from app.services.project_overlay_preflight_service import build_project_overlay_preflight
from app.services.tracking_service import get_tracking_summary


def _load_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, str)]


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _action(
    action: str,
    label: str,
    description: str,
    route: str,
    *,
    enabled: bool = True,
    reason: str | None = None,
    blockers: list[str] | None = None,
    route_query: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "action": action,
        "label": label,
        "description": description,
        "route": route,
        "enabled": enabled,
        "reason": reason,
        "blockers": blockers or [],
        "route_query": route_query or {},
    }


def _step(key: str, label: str, status: str, summary: str, action: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "summary": summary,
        "action": action,
    }


def _profile_summary(profile: LearnerProfile | None) -> str:
    if profile is None:
        return "尚未采集画像，路径无法体现基础、偏好和时间预算。"
    return f"数学 {profile.math_level} / 编程 {profile.coding_level} / 机器学习 {profile.ml_level}，每周 {profile.weekly_hours:g} 小时。"


def _path_summary(latest_plan: Any | None) -> str:
    if latest_plan is None:
        return "尚未生成学习路径。"
    if latest_plan.total_hours is None:
        return f"已生成 v{latest_plan.version}。"
    return f"已生成 v{latest_plan.version}，约 {latest_plan.total_hours:g} 小时。"


def _overlay_status(preflight: dict[str, Any]) -> tuple[str, str]:
    counts = preflight.get("counts") if isinstance(preflight.get("counts"), dict) else {}
    active_total = _as_int(counts.get("active_nodes")) + _as_int(counts.get("active_edges"))
    if active_total <= 0:
        return "pending", "尚未创建项目级扩展，可在 Knowledge 中补充图谱外知识。"
    if preflight.get("status") == "blocked":
        return "blocked", str(preflight.get("summary") or "扩展图谱存在阻塞问题。")
    if preflight.get("status") == "warning":
        return "warning", str(preflight.get("summary") or "扩展图谱存在待处理状态。")
    return "completed", str(preflight.get("summary") or "扩展图谱可用于增强路径。")


def _overlay_blockers(preflight: dict[str, Any]) -> list[str]:
    counts = preflight.get("counts") if isinstance(preflight.get("counts"), dict) else {}
    node_counts = counts.get("nodes") if isinstance(counts.get("nodes"), dict) else {}
    edge_counts = counts.get("edges") if isinstance(counts.get("edges"), dict) else {}
    blockers: list[str] = []
    invalid = _as_int(node_counts.get("invalid")) + _as_int(edge_counts.get("invalid"))
    pending_review = _as_int(node_counts.get("pending_review")) + _as_int(edge_counts.get("pending_review"))
    planning_disabled = _as_int(node_counts.get("planning_disabled")) + _as_int(edge_counts.get("planning_disabled"))
    if invalid:
        blockers.append(f"{invalid} 个扩展候选校验失败")
    if pending_review:
        blockers.append(f"{pending_review} 个扩展候选等待人工审核")
    if planning_disabled:
        blockers.append(f"{planning_disabled} 个已确认候选尚未启用规划")
    for item in list(preflight.get("blocking_items") or [])[:2]:
        if isinstance(item, dict) and item.get("message"):
            blockers.append(str(item["message"]))
    return blockers


def _pick_recommended_action(
    *,
    goal_confirmed: bool,
    profile_completed: bool,
    project_status: str,
    overlay_preflight: dict[str, Any],
    overlay_step_status: str,
    path_exists: bool,
    tracking_summary: dict[str, Any],
    tracking_event_count: int,
) -> dict[str, Any]:
    counts = overlay_preflight.get("counts") if isinstance(overlay_preflight.get("counts"), dict) else {}
    node_counts = counts.get("nodes") if isinstance(counts.get("nodes"), dict) else {}
    edge_counts = counts.get("edges") if isinstance(counts.get("edges"), dict) else {}
    pending_review = _as_int(node_counts.get("pending_review")) + _as_int(edge_counts.get("pending_review"))
    invalid = _as_int(node_counts.get("invalid")) + _as_int(edge_counts.get("invalid"))
    planning_disabled = _as_int(node_counts.get("planning_disabled")) + _as_int(edge_counts.get("planning_disabled"))

    if not goal_confirmed:
        return _action(
            "reconfirm_goal",
            "重新确认目标",
            "目标解析结果不完整，先确认学习目标边界。",
            "/project",
            reason="正式路径必须绑定可解释的目标节点。",
            blockers=["缺少已确认目标节点"],
            route_query={"mode": "reconfirm"},
        )
    if project_status == "extension_review":
        return _action(
            "review_overlay",
            "审核扩展草稿",
            "该项目正在等待项目级图谱扩展审核。",
            "/knowledge",
            reason="项目创建时识别到图谱外目标，需要先审核项目级候选。",
            blockers=["项目状态为 extension_review"],
            route_query={"scope": "project"},
        )
    if overlay_step_status == "blocked":
        return _action(
            "fix_overlay",
            "处理图谱阻塞",
            "增强图谱存在阻塞项，先在 Knowledge 中修复。",
            "/knowledge",
            reason="阻塞项会破坏增强图谱的可规划性。",
            blockers=_overlay_blockers(overlay_preflight),
            route_query={"scope": "project"},
        )
    if pending_review or invalid or planning_disabled:
        return _action(
            "review_overlay",
            "审核扩展候选",
            "存在待审核、需复核或未启用规划的扩展候选。",
            "/knowledge",
            reason="只有通过校验、已确认且启用规划的候选才会进入增强路径。",
            blockers=_overlay_blockers(overlay_preflight),
            route_query={"scope": "project"},
        )
    if not profile_completed:
        return _action(
            "complete_profile",
            "继续画像采集",
            "补全基础、偏好和时间预算后才能生成个性化路径。",
            "/project",
            reason="画像参数会影响补强权重、排序和时间预算提示。",
            blockers=["尚未完成学习者画像"],
        )
    if not path_exists:
        return _action(
            "generate_path",
            "生成学习路径",
            "目标和画像已就绪，可以生成阶段化学习路径。",
            "/path",
            reason="目标、画像和扩展预检均已就绪。",
            route_query={"scope": "path"},
        )
    if _as_int(tracking_summary.get("total_nodes")) <= 0:
        return _action("view_path", "查看学习路径", "路径已生成，先检查阶段与知识点安排。", "/path", route_query={"scope": "path"})
    if tracking_event_count <= 0:
        return _action(
            "start_tracking",
            "开始学习跟踪",
            "路径已生成，可以在路径页标记开始、完成或跳过。",
            "/path",
            reason="跟踪事件会驱动进度统计和后续重规划依据。",
            route_query={"scope": "path"},
        )
    if float(tracking_summary.get("completion_rate") or 0.0) >= 1.0:
        return _action("review_or_replan", "复盘或重规划", "当前路径已完成，可以复盘或根据反馈重规划。", "/path", route_query={"scope": "path"})
    return _action("continue_tracking", "继续学习跟踪", "根据当前进度继续推进，必要时触发重规划。", "/path", route_query={"scope": "path"})


async def build_project_workflow_state(db: AsyncSession, project_id: str) -> dict[str, Any]:
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    profile = (
        await db.execute(select(LearnerProfile).where(LearnerProfile.project_id == project_id).limit(1))
    ).scalar_one_or_none()
    latest_plan = await get_latest_plan(db, project_id)
    tracking_events = await get_events(db, project_id)
    overlay_preflight = await build_project_overlay_preflight(db, project_id=project_id, domain=project.domain)

    target_node_ids = _load_list(project.confirmed_target_node_ids_json)
    missing_concepts = _load_list(project.missing_concepts_json)
    goal_confirmed = bool(project.confirmed_candidate_id and target_node_ids)
    profile_completed = profile is not None
    path_node_ids = extract_plan_node_ids(latest_plan.plan_json if latest_plan else None)
    tracking_summary = await get_tracking_summary(db, project_id, path_node_ids) if latest_plan else {
        "total_nodes": 0,
        "completed": 0,
        "in_progress": 0,
        "skipped": 0,
        "pending": 0,
        "completion_rate": 0.0,
    }

    overlay_step_status, overlay_summary = _overlay_status(overlay_preflight)
    path_exists = latest_plan is not None
    recommended_action = _pick_recommended_action(
        goal_confirmed=goal_confirmed,
        profile_completed=profile_completed,
        project_status=project.status,
        overlay_preflight=overlay_preflight,
        overlay_step_status=overlay_step_status,
        path_exists=path_exists,
        tracking_summary=tracking_summary,
        tracking_event_count=len(tracking_events),
    )

    steps = [
        _step(
            "goal",
            "目标确认",
            "completed" if goal_confirmed else "active",
            f"已确认 {len(target_node_ids)} 个目标节点。" if goal_confirmed else "目标尚未完成解析确认。",
            _action("reconfirm_goal", "重新确认", "重新解析或修正学习目标。", "/project"),
        ),
        _step(
            "profile",
            "画像采集",
            "completed" if profile_completed else "active" if goal_confirmed else "pending",
            _profile_summary(profile),
            _action("complete_profile", "填写画像", "补全学习者画像。", "/project"),
        ),
        _step(
            "overlay",
            "图谱扩展",
            overlay_step_status,
            overlay_summary,
            _action("review_overlay", "进入 Knowledge", "审核或补充项目级扩展候选。", "/knowledge"),
        ),
        _step(
            "path",
            "路径规划",
            "completed" if path_exists else "active" if profile_completed else "pending",
            _path_summary(latest_plan),
            _action("generate_path", "生成路径", "生成或刷新阶段化学习路径。", "/path"),
        ),
        _step(
            "tracking",
            "学习跟踪",
            "completed" if tracking_summary["completion_rate"] >= 1.0 and tracking_summary["total_nodes"] > 0 else "active" if path_exists else "pending",
            f"完成率 {tracking_summary['completion_rate']:.0%}，已记录 {len(tracking_events)} 条事件。" if path_exists else "生成路径后可记录学习进度。",
            _action("continue_tracking", "查看路径", "进入路径页跟踪学习进度。", "/path"),
        ),
    ]

    return {
        "project_id": project.id,
        "project_status": project.status,
        "updated_at": project.updated_at,
        "current_stage": recommended_action["action"],
        "recommended_next_action": recommended_action,
        "steps": steps,
        "goal": {
            "confirmed": goal_confirmed,
            "goal_type": project.goal_type,
            "target_node_count": len(target_node_ids),
            "missing_concepts": missing_concepts,
            "partial_accepted": project.partial_accepted,
        },
        "profile": {
            "completed": profile_completed,
            "summary": _profile_summary(profile),
            "weekly_hours": profile.weekly_hours if profile else None,
            "deadline_weeks": profile.deadline_weeks if profile else None,
        },
        "overlay": {
            "status": overlay_preflight.get("status"),
            "summary": overlay_preflight.get("summary"),
            "counts": overlay_preflight.get("counts") or {},
            "blocking_items": overlay_preflight.get("blocking_items") or [],
            "warning_items": overlay_preflight.get("warning_items") or [],
        },
        "path": {
            "exists": path_exists,
            "path_id": latest_plan.id if latest_plan else None,
            "version": latest_plan.version if latest_plan else None,
            "total_hours": latest_plan.total_hours if latest_plan else None,
            "budget_status": latest_plan.budget_status if latest_plan else None,
            "node_count": len(path_node_ids),
            "created_at": latest_plan.created_at if latest_plan else None,
        },
        "tracking": {
            "available": path_exists,
            "event_count": len(tracking_events),
            **tracking_summary,
        },
    }
