from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.init_db import backfill_all_legacy_projects
from app.models.sqlite_models import Base, LearningProject

_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


def _make_mock_pack(*, version: str = "1.3.0") -> MagicMock:
    pack = MagicMock()
    pack.manifest = {"version": version}
    pack.nodes_by_id = {
        "ml_c09": {"id": "ml_c09", "name": "逻辑回归"},
        "ml_d08": {"id": "ml_d08", "name": "模型评估"},
        "ml_e03": {"id": "ml_e03", "name": "实践项目"},
        "ml_e07": {"id": "ml_e07", "name": "机器学习概览"},
    }
    pack.goal_templates = [
        {
            "id": "problem_understand_001",
            "goal_type": "problem",
            "pattern": ["逻辑回归", "分类"],
            "target_node_ids": ["ml_c09"],
            "mode": "efficient",
            "description": "理解逻辑回归的分类原理",
        }
    ]
    return pack


@pytest.fixture(autouse=True)
async def _fresh_schema():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _insert_project(**kwargs) -> str:
    project = LearningProject(
        title=kwargs.get("title", "Test Project"),
        goal_text=kwargs.get("goal_text", "我想搞懂逻辑回归为什么能做分类"),
        goal_type=kwargs.get("goal_type", "problem"),
        domain=kwargs.get("domain", "machine_learning"),
        requested_goal_type=kwargs.get("requested_goal_type"),
        auto_detected_goal_type=kwargs.get("auto_detected_goal_type"),
        confirmed_target_node_ids_json=kwargs.get("confirmed_target_node_ids_json"),
        confirmed_mode=kwargs.get("confirmed_mode"),
        confirmed_description=kwargs.get("confirmed_description"),
        confirmed_template_id=kwargs.get("confirmed_template_id"),
        confirmed_resolve_source=kwargs.get("confirmed_resolve_source"),
        confirmed_source_breakdown_json=kwargs.get("confirmed_source_breakdown_json"),
        confirmed_candidate_id=kwargs.get("confirmed_candidate_id"),
        resolution_pack_version=kwargs.get("resolution_pack_version"),
        resolution_confirmed_at=kwargs.get("resolution_confirmed_at"),
    )
    async with _Session() as db:
        db.add(project)
        await db.commit()
        await db.refresh(project)
        return project.id


async def test_valid_legacy_project_gets_backfilled():
    project_id = await _insert_project()
    mock_pack = _make_mock_pack()

    with patch("app.db.init_db.get_domain_pack_service", return_value=mock_pack):
        async with _Session() as db:
            count = await backfill_all_legacy_projects(db)
            await db.commit()

    assert count == 1

    async with _Session() as db:
        project = await db.get(LearningProject, project_id)

    assert project is not None
    assert project.requested_goal_type == "problem"
    assert project.auto_detected_goal_type == "problem"
    assert project.confirmed_target_node_ids_json == json.dumps(["ml_c09"], ensure_ascii=False, sort_keys=True)
    assert project.confirmed_mode == "efficient"
    assert project.confirmed_description == "理解逻辑回归的分类原理"
    assert project.confirmed_template_id == "problem_understand_001"
    assert project.confirmed_resolve_source == "template"
    assert project.confirmed_source_breakdown_json == json.dumps({"template": 1.0}, ensure_ascii=False, sort_keys=True)
    assert project.confirmed_candidate_id == f"legacy:{project_id}"
    assert project.resolution_pack_version == "1.3.0"
    assert isinstance(project.resolution_confirmed_at, datetime)
    assert project.resolution_confirmed_at.tzinfo is None


async def test_already_backfilled_project_remains_unchanged():
    project_id = await _insert_project(
        confirmed_target_node_ids_json='["ml_c09"]',
        confirmed_mode="steady",
        confirmed_description="original description",
        confirmed_template_id="existing_template",
        confirmed_resolve_source="template",
        confirmed_source_breakdown_json='{"template": 1.0}',
        confirmed_candidate_id="legacy:existing",
        resolution_pack_version="0.9.0",
        resolution_confirmed_at=datetime(2025, 1, 1, 0, 0, 0),
        requested_goal_type="problem",
        auto_detected_goal_type="problem",
    )
    mock_pack = _make_mock_pack(version="2.0.0")

    with patch("app.db.init_db.get_domain_pack_service", return_value=mock_pack):
        async with _Session() as db:
            count = await backfill_all_legacy_projects(db)
            await db.commit()

    assert count == 0

    async with _Session() as db:
        project = await db.get(LearningProject, project_id)

    assert project.confirmed_target_node_ids_json == '["ml_c09"]'
    assert project.confirmed_mode == "steady"
    assert project.confirmed_description == "original description"
    assert project.confirmed_template_id == "existing_template"
    assert project.confirmed_resolve_source == "template"
    assert project.confirmed_source_breakdown_json == '{"template": 1.0}'
    assert project.confirmed_candidate_id == "legacy:existing"
    assert project.resolution_pack_version == "0.9.0"


async def test_fallback_result_causes_backfill_failure():
    await _insert_project(goal_text="bad fallback case", goal_type="problem")
    mock_pack = _make_mock_pack()
    bad_result = {
        "goal_text": "bad fallback case",
        "goal_type": "problem",
        "target_node_ids": ["ml_c09"],
        "mode": "efficient",
        "description": "bad fallback case",
        "template_id": None,
        "resolve_source": "fallback",
    }

    with patch("app.db.init_db.get_domain_pack_service", return_value=mock_pack), patch(
        "app.db.init_db.resolve_goal", return_value=bad_result
    ):
        with pytest.raises(ValueError, match="fallback"):
            async with _Session() as db:
                await backfill_all_legacy_projects(db)
                await db.commit()


async def test_domain_default_result_causes_backfill_failure():
    await _insert_project(goal_text="bad domain default case", goal_type="domain")
    mock_pack = _make_mock_pack()
    bad_result = {
        "goal_text": "bad domain default case",
        "goal_type": "domain",
        "target_node_ids": ["ml_e07"],
        "mode": "steady",
        "description": "bad domain default case",
        "template_id": None,
        "resolve_source": "domain_default",
    }

    with patch("app.db.init_db.get_domain_pack_service", return_value=mock_pack), patch(
        "app.db.init_db.resolve_goal", return_value=bad_result
    ):
        with pytest.raises(ValueError, match="domain_default"):
            async with _Session() as db:
                await backfill_all_legacy_projects(db)
                await db.commit()


async def test_backfill_disables_llm_calls():
    await _insert_project(goal_text="totally unmatched text", goal_type="problem")
    mock_pack = _make_mock_pack()
    mock_pack.goal_templates = []

    with patch("app.db.init_db.get_domain_pack_service", return_value=mock_pack), patch(
        "app.services.goal_service._jieba_match_nodes", return_value=[]
    ), patch(
        "app.services.goal_service._llm_match_nodes",
        side_effect=AssertionError("LLM should not be called during backfill"),
    ):
        with pytest.raises(ValueError, match="fallback"):
            async with _Session() as db:
                await backfill_all_legacy_projects(db)
                await db.commit()


async def test_backfill_transactional_no_partial_commit_on_invalid_project():
    valid_id = await _insert_project(
        title="Valid Project",
        goal_text="我想搞懂逻辑回归为什么能做分类",
        goal_type="problem",
    )
    invalid_id = await _insert_project(
        title="Invalid Project",
        goal_text="invalid project text",
        goal_type="domain",
    )
    mock_pack = _make_mock_pack()

    def _resolve_side_effect(goal_text, goal_type_override, templates, nodes_by_id, **kwargs):
        if goal_text == "invalid project text":
            return {
                "goal_text": goal_text,
                "goal_type": "domain",
                "target_node_ids": ["ml_e07"],
                "mode": "steady",
                "description": goal_text,
                "template_id": None,
                "resolve_source": "domain_default",
            }
        return {
            "goal_text": goal_text,
            "goal_type": "problem",
            "target_node_ids": ["ml_c09"],
            "mode": "efficient",
            "description": "理解逻辑回归的分类原理",
            "template_id": "problem_understand_001",
            "resolve_source": "template",
        }

    with patch("app.db.init_db.get_domain_pack_service", return_value=mock_pack), patch(
        "app.db.init_db.resolve_goal", side_effect=_resolve_side_effect
    ):
        with pytest.raises(ValueError):
            async with _Session() as db:
                await backfill_all_legacy_projects(db)
                await db.commit()

    async with _Session() as db:
        valid_project = await db.get(LearningProject, valid_id)
        invalid_project = await db.get(LearningProject, invalid_id)

    assert valid_project.confirmed_target_node_ids_json is None
    assert valid_project.confirmed_resolve_source is None
    assert invalid_project.confirmed_target_node_ids_json is None
    assert invalid_project.confirmed_resolve_source is None
