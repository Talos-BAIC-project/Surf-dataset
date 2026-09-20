"""数据集加载：几何 IR + YAML 语义标注（bbox 弱标注）合并。"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path

import yaml

from .config import SECTIONS_DIR
from .geometry import SectionGeometry, load_section_geometry


@dataclass
class Region:
    """YAML 中的一条语义区域弱标注。"""
    name: str
    function: str            # structural / stiffener / enclosed / cavity / connection / ...
    bbox: dict               # 原样保留（x,y,width,height | x,y,depth,width | radius,position | radius,x,y）
    notes: str = ""

    @property
    def rect(self) -> tuple[float, float, float, float] | None:
        """轴对齐矩形 (x0, y0, x1, y1)；倒角类无矩形时返回 None。"""
        b = self.bbox or {}
        if "x" not in b or "y" not in b:
            return None
        x, y = float(b["x"]), float(b["y"])
        if "height" in b and "width" in b:
            return (x, y, x + float(b["width"]), y + float(b["height"]))
        if "depth" in b and "width" in b:
            # 凹槽：depth 沿水平方向，width 沿竖直方向（数据集约定）
            return (x, y, x + float(b["depth"]), y + float(b["width"]))
        return None


@dataclass
class SectionRecord:
    section_id: str
    shape_family: str        # 如 目_shape / B_shape / ji_shape
    topology: str            # closed / open
    geometry: SectionGeometry
    regions: list[Region] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def yaml_bbox(self) -> tuple[float, float]:
        bb = ((self.meta.get("geometry") or {}).get("bounding_box") or {})
        return float(bb.get("width", 0.0)), float(bb.get("height", 0.0))

    @property
    def feature_statistics(self) -> dict:
        return self.meta.get("feature_statistics") or {}


def _normalize_function(region: dict) -> str:
    fn = region.get("function")
    name = (region.get("name") or "").lower()
    if fn:
        return str(fn)
    # 少数区域缺 function：按名称回退（chamfer_* / fillet_* 视为过渡特征）
    if name.startswith(("chamfer", "fillet")):
        return "transition"
    return "unknown"


def load_section_record(section_dir: Path) -> SectionRecord | None:
    section_id = section_dir.name
    yaml_path = section_dir / f"{section_id}.yaml"
    if not yaml_path.exists():
        return None
    meta = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    geometry = load_section_geometry(section_dir)
    if geometry is None or not geometry.curves:
        return None
    # Keep a relocatable source manifest in memory and in generated metadata.
    # Only basenames are recorded; absolute checkout paths would make the
    # dataset non-reproducible and leak local filesystem layout.
    source_paths = [yaml_path, section_dir / f"{section_id}.{geometry.source}"]
    manifest = [
        {"file": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in source_paths if p.exists()
    ]
    meta.setdefault("_provenance", {})["source_files"] = manifest
    shape = meta.get("shape") or {}
    regions = [
        Region(
            name=r.get("name") or f"region_{i}",
            function=_normalize_function(r),
            bbox=r.get("bbox") or {},
            notes=r.get("notes") or "",
        )
        for i, r in enumerate(meta.get("regions") or [])
    ]
    return SectionRecord(
        section_id=section_id,
        shape_family=str(shape.get("primary") or "unknown"),
        topology=str(shape.get("topology") or "unknown"),
        geometry=geometry,
        regions=regions,
        meta=meta,
    )


def load_all_sections(sections_dir: Path | None = None) -> list[SectionRecord]:
    root = Path(sections_dir) if sections_dir else SECTIONS_DIR
    records = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        rec = load_section_record(d)
        if rec is not None:
            records.append(rec)
    return records
