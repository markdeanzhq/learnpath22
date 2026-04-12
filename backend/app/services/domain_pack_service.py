"""Domain Pack 加载服务：读取 JSON、DAG 校验、字段完整性校验"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import networkx as nx

PACK_DIR = Path(__file__).resolve().parent.parent / "domain_packs"
ALLOWED_DOMAINS = {"machine_learning"}


class DomainPackService:
    def __init__(self, domain: str = "machine_learning"):
        if domain not in ALLOWED_DOMAINS:
            raise ValueError(f"不支持的领域: {domain}，可选: {ALLOWED_DOMAINS}")
        self.domain = domain
        self._base = (PACK_DIR / domain).resolve()
        if not self._base.is_relative_to(PACK_DIR.resolve()):
            raise ValueError("无效的领域路径")
        self.manifest: dict[str, Any] = {}
        self.nodes: list[dict[str, Any]] = []
        self.nodes_by_id: dict[str, dict[str, Any]] = {}
        self.requires_edges: list[dict[str, Any]] = []
        self.related_edges: list[dict[str, Any]] = []
        self.stage_rules: dict[str, Any] = {}
        self.goal_templates: list[dict[str, Any]] = []
        self.scoring_config: dict[str, Any] = {}
        self.calibration: dict[str, Any] = {}
        self.requires_adj: dict[str, list[str]] = defaultdict(list)
        self.requires_rev_adj: dict[str, list[str]] = defaultdict(list)

    def load(self) -> None:
        self.manifest = self._read("manifest.json")
        self.nodes = self._read("nodes.json")
        self.nodes_by_id = {n["id"]: n for n in self.nodes}
        self.requires_edges = self._read("requires_edges.json")
        self.related_edges = self._read("related_edges.json")
        self.stage_rules = self._read("stage_rules.json")
        self.goal_templates = self._read("goal_templates.json")
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

    def validate_dag(self) -> bool:
        g = nx.DiGraph()
        for edge in self.requires_edges:
            g.add_edge(edge["source"], edge["target"])
        if not nx.is_directed_acyclic_graph(g):
            cycles = list(nx.simple_cycles(g))
            raise ValueError(f"知识图谱存在环: {cycles}")
        return True

    def validate_fields(self) -> list[str]:
        required = [
            "id", "name", "group", "category", "difficulty_final",
            "importance_final", "estimated_hours", "req_math",
            "req_coding", "req_ml", "theory_weight", "practice_weight",
        ]
        errors: list[str] = []
        for node in self.nodes:
            for field in required:
                if field not in node:
                    errors.append(f"节点 {node.get('id', '?')} 缺少字段 {field}")
        return errors

    def _read(self, filename: str) -> Any:
        path = self._base / filename
        with open(path, encoding="utf-8") as f:
            return json.load(f)


_pack_service: DomainPackService | None = None


def get_domain_pack_service(
    domain: str = "machine_learning",
    force_reload: bool = False,
) -> DomainPackService:
    global _pack_service
    if force_reload or _pack_service is None or _pack_service.domain != domain:
        _pack_service = DomainPackService(domain)
        _pack_service.load()
        _pack_service.validate_dag()
    return _pack_service
