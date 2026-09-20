"""查询样本构建：silver 金标 -> 可训练/可评估的 (查询, 实体集合) 样本。

两种查询粒度：
- generic  : "腔体" / "加强筋" -> 该 label 在截面内的全部实体（并集）
- specific : "chamber_2" / "stiffener_a" -> 指定序数的单个区域实体集
  仅当截面内同 label 区域 >= 2 时生成（否则与 generic 重复）。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .dataset import SectionRecord
from .labels import LabelRegistry
from .silver import SilverTarget


@dataclass
class QuerySample:
    sample_id: str
    section_id: str
    family: str
    label_id: str
    entity_type: str                    # face | curve | point
    kind: str                           # generic | specific
    query_text: str                     # 演示用查询文本（中文别名 / region 名）
    ordinal: int | None = None
    target_curves: list[str] = field(default_factory=list)
    target_faces: list[str] = field(default_factory=list)
    target_points: list[str] = field(default_factory=list)
    source_regions: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def primary_targets(self) -> list[str]:
        if self.entity_type == "face":
            return self.target_faces
        if self.entity_type == "point":
            return self.target_points
        return self.target_curves


def build_query_samples(rec: SectionRecord, targets: list[SilverTarget],
                        registry: LabelRegistry) -> list[QuerySample]:
    samples: list[QuerySample] = []
    by_label: dict[str, list[SilverTarget]] = {}
    for t in targets:
        if t.is_empty:
            continue
        by_label.setdefault(t.label_id, []).append(t)

    for label_id, group in sorted(by_label.items()):
        profile = registry.by_id.get(label_id)
        caption = profile.caption_zh if profile else label_id
        # 实体类型以多数为准（chamfer 角点回退可能局部改变类型）
        etypes = [t.entity_type for t in group]
        entity_type = max(set(etypes), key=etypes.count)

        union_c: list[str] = []
        union_f: list[str] = []
        union_p: list[str] = []
        flags: set[str] = set()
        for t in group:
            for c in t.curve_names:
                if c not in union_c:
                    union_c.append(c)
            for f in t.face_ids:
                if f not in union_f:
                    union_f.append(f)
            for p in t.point_names:
                if p not in union_p:
                    union_p.append(p)
            flags.update(f for f in t.flags if f != "synthetic")
        samples.append(QuerySample(
            sample_id=f"{rec.section_id}::{label_id}::generic",
            section_id=rec.section_id, family=rec.shape_family,
            label_id=label_id, entity_type=entity_type, kind="generic",
            query_text=caption,
            target_curves=union_c, target_faces=union_f, target_points=union_p,
            source_regions=[t.region_name for t in group],
            flags=sorted(flags),
        ))

        # specific：同 label 有多个带序数的区域
        ordinal_group = [t for t in group if t.ordinal is not None]
        if len(ordinal_group) >= 2:
            for t in ordinal_group:
                samples.append(QuerySample(
                    sample_id=f"{rec.section_id}::{label_id}::{t.region_name}",
                    section_id=rec.section_id, family=rec.shape_family,
                    label_id=label_id, entity_type=t.entity_type, kind="specific",
                    query_text=t.region_name, ordinal=t.ordinal,
                    target_curves=list(t.curve_names), target_faces=list(t.face_ids),
                    target_points=list(t.point_names),
                    source_regions=[t.region_name],
                    flags=[f for f in t.flags if f != "synthetic"],
                ))
    return samples


def save_samples(samples: list[QuerySample], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for s in samples:
            fh.write(json.dumps(asdict(s), ensure_ascii=False) + "\n")


def load_samples(path: Path) -> list[QuerySample]:
    out = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                out.append(QuerySample(**json.loads(line)))
    return out
