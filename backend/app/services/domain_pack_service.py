"""Domain Pack 加载服务：读取 JSON、DAG 校验、字段完整性校验"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import networkx as nx

PACK_DIR = Path(__file__).resolve().parent.parent / "domain_packs"
DEFAULT_DOMAIN = "machine_learning"
_PUBLIC_GOAL_TYPES = frozenset({"domain", "concept", "problem"})


@dataclass(frozen=True)
class DomainPackRegistry:
    default_domain: str
    enabled_domains: frozenset[str]

    def resolve_domain(self, domain: str | None = None) -> str:
        if domain is None:
            if self.default_domain in self.enabled_domains:
                return self.default_domain
            if len(self.enabled_domains) == 1:
                return next(iter(self.enabled_domains))
            if not self.enabled_domains:
                raise ValueError("未发现可用的 Domain Pack")
            raise ValueError(f"默认领域 {self.default_domain} 不在已启用 pack 中")
        if domain not in self.enabled_domains:
            raise ValueError(f"不支持的领域: {domain}，可选: {set(self.enabled_domains)}")
        return domain


@dataclass(frozen=True)
class DomainPackContract:
    domain: str
    version: str
    supported_goal_types: tuple[str, ...]
    default_goal_policy: Mapping[str, Any]
    node_count: int
    pack_hash: str
    nodes_by_id: Mapping[str, dict[str, Any]]
    goal_templates: tuple[dict[str, Any], ...]
    requires_adj: Mapping[str, tuple[str, ...]]
    requires_rev_adj: Mapping[str, tuple[str, ...]]


_registry: DomainPackRegistry | None = None
_registry_pack_dir: Path | None = None
_pack_services: dict[str, "DomainPackService"] = {}
_pack_services_pack_dir: Path | None = None


def _discover_enabled_domains(pack_dir: Path) -> frozenset[str]:
    if not pack_dir.exists():
        return frozenset()
    enabled_domains = [
        path.name
        for path in sorted(pack_dir.iterdir(), key=lambda item: item.name)
        if path.is_dir() and (path / "manifest.json").exists()
    ]
    return frozenset(enabled_domains)


def get_domain_pack_registry(force_reload: bool = False) -> DomainPackRegistry:
    global _registry, _registry_pack_dir

    resolved_pack_dir = PACK_DIR.resolve()
    if force_reload or _registry is None or _registry_pack_dir != resolved_pack_dir:
        enabled_domains = _discover_enabled_domains(PACK_DIR)
        if DEFAULT_DOMAIN in enabled_domains:
            default_domain = DEFAULT_DOMAIN
        elif enabled_domains:
            default_domain = sorted(enabled_domains)[0]
        else:
            default_domain = DEFAULT_DOMAIN
        _registry = DomainPackRegistry(
            default_domain=default_domain,
            enabled_domains=enabled_domains,
        )
        _registry_pack_dir = resolved_pack_dir
    return _registry


def _canonicalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonicalize_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonicalize_value(item) for item in value]
    return value


def _sort_by_id(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: str(item.get("id", "")))


def _edge_sort_key(edge: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(edge.get("source", "")),
        str(edge.get("target", "")),
        str(edge.get("type", "")),
        str(edge.get("reason", "")),
    )


def build_canonical_pack_payload(pack: Any) -> dict[str, Any]:
    return {
        "manifest": _canonicalize_value(getattr(pack, "manifest", {})),
        "nodes": [_canonicalize_value(node) for node in _sort_by_id(list(getattr(pack, "nodes", [])))],
        "requires_edges": [
            _canonicalize_value(edge)
            for edge in sorted(list(getattr(pack, "requires_edges", [])), key=_edge_sort_key)
        ],
        "related_edges": [
            _canonicalize_value(edge)
            for edge in sorted(list(getattr(pack, "related_edges", [])), key=_edge_sort_key)
        ],
        "stage_rules": _canonicalize_value(getattr(pack, "stage_rules", {})),
        "stages": [_canonicalize_value(stage) for stage in _sort_by_id(list(getattr(pack, "stages", [])))],
        "goal_templates": [
            _canonicalize_value(template)
            for template in _sort_by_id(list(getattr(pack, "goal_templates", [])))
        ],
        "scoring_config": _canonicalize_value(getattr(pack, "scoring_config", {})),
        "resources": [
            _canonicalize_value(resource)
            for resource in _sort_by_id(list(getattr(pack, "resources", [])))
        ],
    }


def build_canonical_pack_hash(pack: Any) -> str:
    encoded = json.dumps(
        build_canonical_pack_payload(pack),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class DomainPackService:
    def __init__(self, domain: str | None = None):
        self._registry = get_domain_pack_registry()
        self.domain = self._registry.resolve_domain(domain)
        self._base = (PACK_DIR / self.domain).resolve()
        if not self._base.is_relative_to(PACK_DIR.resolve()):
            raise ValueError("无效的领域路径")
        self.manifest: dict[str, Any] = {}
        self.nodes: list[dict[str, Any]] = []
        self.nodes_by_id: dict[str, dict[str, Any]] = {}
        self.requires_edges: list[dict[str, Any]] = []
        self.related_edges: list[dict[str, Any]] = []
        self.stages: list[dict[str, Any]] = []
        self.stages_by_id: dict[str, dict[str, Any]] = {}
        self.resources: list[dict[str, Any]] = []
        self.resources_by_id: dict[str, dict[str, Any]] = {}
        self.stage_rules: dict[str, Any] = {}
        self.goal_templates: list[dict[str, Any]] = []
        self.scoring_config: dict[str, Any] = {}
        self.calibration: dict[str, Any] = {}
        self.requires_adj: dict[str, list[str]] = defaultdict(list)
        self.requires_rev_adj: dict[str, list[str]] = defaultdict(list)
        self.pack_hash: str = ""
        self.contract: DomainPackContract | None = None

    def load(self) -> None:
        self.manifest = self._read("manifest.json")
        self.nodes = self._normalize_nodes(self._read("nodes.json"))
        self.nodes_by_id = {n["id"]: n for n in self.nodes}
        self.requires_edges = self._read("requires_edges.json")
        self.related_edges = self._read("related_edges.json")
        self.stage_rules = self._read("stage_rules.json")
        self.stages = self._read("stages.json")
        self.stages_by_id = {
            stage["id"]: stage for stage in self.stages if "id" in stage
        }
        self.resources = self._read("resources.json")
        self.resources_by_id = {
            resource["id"]: resource
            for resource in self.resources
            if "id" in resource
        }
        self.goal_templates = self._normalize_goal_templates(self._read("goal_templates.json"))
        self.scoring_config = self._read("scoring_config.json")
        self.calibration = self._read("calibration_overrides.json")

        for anchor in self.calibration.get("anchors", []):
            node = self.nodes_by_id.get(anchor["node_id"])
            if node is None:
                continue
            if "difficulty_final" in anchor:
                node["difficulty_final"] = anchor["difficulty_final"]
            if "importance_final" in anchor:
                node["importance_final"] = anchor["importance_final"]

        self.requires_adj = defaultdict(list)
        self.requires_rev_adj = defaultdict(list)
        for edge in self.requires_edges:
            src, tgt = edge["source"], edge["target"]
            self.requires_adj[src].append(tgt)
            self.requires_rev_adj[tgt].append(src)

        field_errors = self.validate_fields()
        if field_errors:
            raise ValueError(f"Domain Pack 字段校验失败: {field_errors}")

        self.validate_dag()
        integrity_result = self.validate_graph_integrity(strict=True)
        if not integrity_result["valid"]:
            raise ValueError(f"图完整性校验失败: {integrity_result['errors']}")

        self.pack_hash = build_canonical_pack_hash(self)
        self.contract = DomainPackContract(
            domain=self.domain,
            version=str(self.manifest.get("version", "")),
            supported_goal_types=tuple(self.manifest.get("supported_goal_types", [])),
            default_goal_policy=self.manifest.get("default_goal_policy", {}),
            node_count=int(self.manifest.get("node_count", len(self.nodes))),
            pack_hash=self.pack_hash,
            nodes_by_id=self.nodes_by_id,
            goal_templates=tuple(self.goal_templates),
            requires_adj={key: tuple(value) for key, value in self.requires_adj.items()},
            requires_rev_adj={key: tuple(value) for key, value in self.requires_rev_adj.items()},
        )

    def _normalize_nodes(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for node in nodes:
            normalized_node = dict(node)
            normalized_node.setdefault("aliases", [])
            normalized_node.setdefault("keywords", [])
            normalized.append(normalized_node)
        return normalized

    def _normalize_goal_templates(
        self,
        templates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for template in templates:
            normalized_template = dict(template)
            normalized_template.setdefault("negative_patterns", [])
            normalized_template.setdefault("priority", 50)
            normalized.append(normalized_template)
        return normalized

    def _build_requires_graph(self) -> nx.DiGraph:
        graph = nx.DiGraph()
        graph.add_nodes_from(self.nodes_by_id)
        graph.add_edges_from((edge["source"], edge["target"]) for edge in self.requires_edges)
        return graph

    def validate_dag(self) -> bool:
        g = self._build_requires_graph()
        if not nx.is_directed_acyclic_graph(g):
            cycles = list(nx.simple_cycles(g))
            raise ValueError(f"知识图谱存在环: {cycles}")
        return True

    def validate_graph_integrity(self, strict: bool = True) -> dict[str, Any]:
        """
        图完整性校验，返回 {"valid": bool, "errors": list[str], "warnings": list[str]}

        检查项：
        1. Node reference check - 边引用的节点必须存在
        2. Duplicate edge check - 不允许重复边
        3. Self-loop check - 不允许自环
        4. Cycle check - 复用 validate_dag
        5. Orphan check - 孤点检测（strict 模式报错）
        6. Main path isolation check - 主路径节点不能孤立
        7. Stage heuristic check - 阶段顺序启发式（仅 warning）
        """
        errors: list[str] = []
        warnings: list[str] = []

        all_node_ids = {n["id"] for n in self.nodes}

        for edge in self.requires_edges:
            if edge["source"] not in all_node_ids:
                errors.append(f"边的 source '{edge['source']}' 不在 nodes.json 中")
            if edge["target"] not in all_node_ids:
                errors.append(f"边的 target '{edge['target']}' 不在 nodes.json 中")

        edge_tuples = [(e["source"], e["target"]) for e in self.requires_edges]
        if len(edge_tuples) != len(set(edge_tuples)):
            errors.append("检测到重复边")

        for edge in self.requires_edges:
            if edge["source"] == edge["target"]:
                errors.append(f"检测到自环: {edge['source']}")

        try:
            self.validate_dag()
        except ValueError as e:
            errors.append(f"DAG 校验失败: {e}")

        in_degree = defaultdict(int)
        out_degree = defaultdict(int)
        for edge in self.requires_edges:
            out_degree[edge["source"]] += 1
            in_degree[edge["target"]] += 1

        orphans = [
            nid for nid in all_node_ids
            if in_degree[nid] == 0 and out_degree[nid] == 0
        ]
        if orphans:
            if strict:
                errors.append(f"检测到孤点节点: {orphans}")
            else:
                warnings.append(f"孤点节点: {orphans}")

        main_path_nodes = {n["id"] for n in self.nodes if n.get("is_main_path")}
        isolated_main = [
            nid for nid in main_path_nodes
            if in_degree[nid] == 0 and out_degree[nid] == 0
        ]
        if isolated_main:
            errors.append(f"主路径节点孤立: {isolated_main}")

        graph = self._build_requires_graph()

        weak_components = nx.number_weakly_connected_components(graph)
        if weak_components != 1:
            message = f"静态图 weak_connected_components 必须为 1，实际为 {weak_components}"
            if strict:
                errors.append(message)
            else:
                warnings.append(message)

        stage_map = {n["id"]: n.get("category", "unknown") for n in self.nodes}
        stage_order = {
            "foundation": 0,
            "concept": 1,
            "algorithm": 2,
            "evaluation": 3,
            "practice": 4,
        }
        for edge in self.requires_edges:
            src_stage = stage_order.get(stage_map.get(edge["source"]), 99)
            tgt_stage = stage_order.get(stage_map.get(edge["target"]), 99)
            if src_stage > tgt_stage:
                warnings.append(
                    f"阶段启发式违反: {edge['source']} ({src_stage}) -> {edge['target']} ({tgt_stage})"
                )

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "weak_connected_components": weak_components,
        }

    @staticmethod
    def _is_string_list(value: Any) -> bool:
        return isinstance(value, list) and all(isinstance(item, str) for item in value)

    @staticmethod
    def _is_valid_priority(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100

    def _validate_supported_goal_types(self, errors: list[str]) -> list[str]:
        supported_goal_types = self.manifest.get("supported_goal_types")
        if not self._is_string_list(supported_goal_types) or not supported_goal_types:
            errors.append("manifest.supported_goal_types 必须为非空字符串数组")
            return []

        normalized_goal_types: list[str] = []
        seen_goal_types: set[str] = set()
        for goal_type in supported_goal_types:
            if goal_type not in _PUBLIC_GOAL_TYPES:
                errors.append(f"manifest.supported_goal_types 包含不支持的 goal_type: {goal_type}")
                continue
            if goal_type in seen_goal_types:
                errors.append(f"manifest.supported_goal_types 存在重复 goal_type: {goal_type}")
                continue
            seen_goal_types.add(goal_type)
            normalized_goal_types.append(goal_type)
        return normalized_goal_types

    def _validate_default_goal_policy(
        self,
        supported_goal_types: set[str],
        errors: list[str],
    ) -> None:
        default_goal_policy = self.manifest.get("default_goal_policy")
        if not isinstance(default_goal_policy, dict):
            errors.append("manifest.default_goal_policy 必须为对象")
            return

        by_goal_type = default_goal_policy.get("by_goal_type")
        if not isinstance(by_goal_type, dict):
            errors.append("manifest.default_goal_policy.by_goal_type 必须为对象")
            return

        for goal_type, policy in by_goal_type.items():
            if goal_type not in supported_goal_types:
                errors.append(f"default_goal_policy 包含未声明的 goal_type: {goal_type}")
                continue
            if not isinstance(policy, dict):
                errors.append(f"default_goal_policy.{goal_type} 必须为对象")
                continue

            required_fields = ("target_node_ids", "mode", "description", "resolve_source")
            for field in required_fields:
                if field not in policy:
                    errors.append(f"default_goal_policy.{goal_type} 缺少字段 {field}")

            target_node_ids = policy.get("target_node_ids")
            if not self._is_string_list(target_node_ids):
                errors.append(f"default_goal_policy.{goal_type}.target_node_ids 必须为字符串数组")
            else:
                for node_id in target_node_ids:
                    if node_id not in self.nodes_by_id:
                        errors.append(
                            f"default_goal_policy.{goal_type}.target_node_ids 引用不存在的节点 {node_id}"
                        )

            for field in ("mode", "description", "resolve_source"):
                value = policy.get(field)
                if value is not None and not isinstance(value, str):
                    errors.append(f"default_goal_policy.{goal_type}.{field} 必须为字符串")

    def validate_fields(self) -> list[str]:
        node_required = [
            "id", "name", "group", "category", "difficulty_final",
            "importance_final", "estimated_hours", "req_math",
            "req_coding", "req_ml", "theory_weight", "practice_weight",
        ]
        stage_required = [
            "id", "name", "order", "description", "category_keys", "node_ids",
        ]
        resource_required = [
            "id", "title", "resource_type", "description", "node_ids", "stage_ids",
        ]
        template_required = [
            "id", "goal_type", "pattern", "target_node_ids", "mode", "description",
        ]
        errors: list[str] = []

        supported_goal_types = set(self._validate_supported_goal_types(errors))

        for node in self.nodes:
            for field in node_required:
                if field not in node:
                    errors.append(f"节点 {node.get('id', '?')} 缺少字段 {field}")

            if not self._is_string_list(node.get("aliases", [])):
                errors.append(f"节点 {node.get('id', '?')} 的 aliases 必须为字符串数组")
            if not self._is_string_list(node.get("keywords", [])):
                errors.append(f"节点 {node.get('id', '?')} 的 keywords 必须为字符串数组")

        seen_stage_ids: set[str] = set()
        seen_stage_orders: set[int] = set()
        for stage in self.stages:
            stage_id = stage.get("id", "?")
            for field in stage_required:
                if field not in stage:
                    errors.append(f"阶段 {stage_id} 缺少字段 {field}")

            if "id" in stage:
                if stage["id"] in seen_stage_ids:
                    errors.append(f"阶段 ID 重复: {stage['id']}")
                else:
                    seen_stage_ids.add(stage["id"])

            if "order" in stage:
                if not isinstance(stage["order"], int):
                    errors.append(f"阶段 {stage_id} 的 order 必须为整数")
                elif stage["order"] in seen_stage_orders:
                    errors.append(f"阶段顺序重复: {stage['order']}")
                else:
                    seen_stage_orders.add(stage["order"])

            category_keys = stage.get("category_keys")
            if isinstance(category_keys, list):
                for category_key in category_keys:
                    mapped_stage = self.stage_rules.get("category_to_stage", {}).get(category_key)
                    if mapped_stage != stage.get("name"):
                        errors.append(
                            f"阶段 {stage_id} 的 category_key {category_key} 映射到 {mapped_stage}，期望 {stage.get('name')}"
                        )
            elif "category_keys" in stage:
                errors.append(f"阶段 {stage_id} 的 category_keys 必须为数组")

            node_ids = stage.get("node_ids")
            if isinstance(node_ids, list):
                for node_id in node_ids:
                    if node_id not in self.nodes_by_id:
                        errors.append(f"阶段 {stage_id} 引用不存在的节点 {node_id}")
            elif "node_ids" in stage:
                errors.append(f"阶段 {stage_id} 的 node_ids 必须为数组")

        ordered_stage_names = [
            stage.get("name")
            for stage in sorted(self.stages, key=lambda item: item.get("order", 0))
        ]
        manifest_stages = self.manifest.get("stages", [])
        if ordered_stage_names != manifest_stages:
            errors.append(
                f"阶段名称顺序与 manifest.stages 不一致: {ordered_stage_names} != {manifest_stages}"
            )
        rule_stages = self.stage_rules.get("stages", [])
        if ordered_stage_names != rule_stages:
            errors.append(
                f"阶段名称顺序与 stage_rules.stages 不一致: {ordered_stage_names} != {rule_stages}"
            )

        for template in self.goal_templates:
            template_id = template.get("id", "?")
            for field in template_required:
                if field not in template:
                    errors.append(f"模板 {template_id} 缺少字段 {field}")

            if not self._is_string_list(template.get("negative_patterns", [])):
                errors.append(f"模板 {template_id} 的 negative_patterns 必须为字符串数组")
            if not self._is_valid_priority(template.get("priority", 50)):
                errors.append(f"模板 {template_id} 的 priority 必须在 0 到 100 之间")

            target_node_ids = template.get("target_node_ids")
            if isinstance(target_node_ids, list):
                for node_id in target_node_ids:
                    if node_id not in self.nodes_by_id:
                        errors.append(f"模板 {template_id} 引用不存在的节点 {node_id}")
            elif "target_node_ids" in template:
                errors.append(f"模板 {template_id} 的 target_node_ids 必须为数组")

            template_goal_type = template.get("goal_type")
            if supported_goal_types and template_goal_type not in supported_goal_types:
                errors.append(
                    f"模板 {template_id} 的 goal_type {template_goal_type} 未在 manifest.supported_goal_types 中声明"
                )

        self._validate_default_goal_policy(supported_goal_types, errors)

        seen_resource_ids: set[str] = set()
        for resource in self.resources:
            resource_id = resource.get("id", "?")
            for field in resource_required:
                if field not in resource:
                    errors.append(f"资源 {resource_id} 缺少字段 {field}")

            if "id" in resource:
                if resource["id"] in seen_resource_ids:
                    errors.append(f"资源 ID 重复: {resource['id']}")
                else:
                    seen_resource_ids.add(resource["id"])

            node_ids = resource.get("node_ids")
            if isinstance(node_ids, list):
                for node_id in node_ids:
                    if node_id not in self.nodes_by_id:
                        errors.append(f"资源 {resource_id} 引用不存在的节点 {node_id}")
            elif "node_ids" in resource:
                errors.append(f"资源 {resource_id} 的 node_ids 必须为数组")

            stage_ids = resource.get("stage_ids")
            if isinstance(stage_ids, list):
                for stage_id in stage_ids:
                    if stage_id not in self.stages_by_id:
                        errors.append(f"资源 {resource_id} 引用不存在的阶段 {stage_id}")
            elif "stage_ids" in resource:
                errors.append(f"资源 {resource_id} 的 stage_ids 必须为数组")

        return errors

    def _read(self, filename: str) -> Any:
        path = self._base / filename
        with open(path, encoding="utf-8") as f:
            return json.load(f)


def get_domain_pack_service(
    domain: str | None = None,
    force_reload: bool = False,
) -> DomainPackService:
    global _pack_services_pack_dir

    resolved_pack_dir = PACK_DIR.resolve()
    if _pack_services_pack_dir != resolved_pack_dir:
        _pack_services.clear()
        _pack_services_pack_dir = resolved_pack_dir

    registry = get_domain_pack_registry(force_reload=force_reload)
    resolved_domain = registry.resolve_domain(domain)
    if force_reload:
        _pack_services.pop(resolved_domain, None)
    if resolved_domain not in _pack_services:
        pack_service = DomainPackService(resolved_domain)
        pack_service.load()
        _pack_services[resolved_domain] = pack_service
    return _pack_services[resolved_domain]
