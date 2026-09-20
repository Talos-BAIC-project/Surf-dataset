"""语料构建：加载数据集 -> 属性图 -> 特征 -> silver 金标 -> 查询样本。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .dataset import SectionRecord, load_all_sections
from .features import SectionFeatures
from .graph import SectionGraph, build_section_graph
from .labels import LabelRegistry
from .samples import QuerySample, build_query_samples
from .silver import SilverTarget, build_silver_targets


@dataclass
class SectionBundle:
    record: SectionRecord
    graph: SectionGraph
    features: SectionFeatures
    silver: list[SilverTarget] = field(default_factory=list)
    samples: list[QuerySample] = field(default_factory=list)


def build_corpus(sections_dir: Path | None = None,
                 registry: LabelRegistry | None = None) -> tuple[list[SectionBundle], LabelRegistry]:
    registry = registry or LabelRegistry.load()
    bundles: list[SectionBundle] = []
    for rec in load_all_sections(sections_dir):
        graph = build_section_graph(rec.geometry)
        features = SectionFeatures(graph)
        silver = build_silver_targets(rec, graph, registry)
        samples = build_query_samples(rec, silver, registry)
        bundles.append(SectionBundle(rec, graph, features, silver, samples))
    return bundles, registry


def all_samples(bundles: list[SectionBundle]) -> list[QuerySample]:
    out: list[QuerySample] = []
    for b in bundles:
        out.extend(b.samples)
    return out


def families(bundles: list[SectionBundle]) -> list[str]:
    return sorted({b.record.shape_family for b in bundles})
