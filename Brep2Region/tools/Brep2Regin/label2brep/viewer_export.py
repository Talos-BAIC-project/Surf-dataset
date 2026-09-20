"""导出前端 viewer 数据（viewer/viewer_data.js）。

诚实性约定：每个截面的预测由"留出其形状族"训练的模型给出（LOFO），
即演示页面上看到的效果与交叉验证一致，不使用见过该形状族的模型。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .labels import LabelRegistry
from .mapper import Mapper
from .models import HybridBank, ModelBank
from .pipeline import SectionBundle


def _round_poly(poly, nd=2):
    return [[round(p[0], nd), round(p[1], nd)] for p in poly]


def export_viewer_data(bundles: list[SectionBundle], registry: LabelRegistry,
                       out_path: Path, metrics_summary: dict | None = None) -> Path:
    # 每个形状族一个 LOFO 模型
    fams = sorted({b.record.shape_family for b in bundles})
    fold_banks: dict[str, HybridBank] = {}
    for fam in fams:
        train = [b for b in bundles if b.record.shape_family != fam]
        lr = ModelBank()
        lr.train(train, [s for b in train for s in b.samples if s.kind == "generic"])
        bank = HybridBank()
        bank.curve_models = lr.curve_models
        bank.face_model = lr.face_model
        fold_banks[fam] = bank

    sections_out = []
    for b in bundles:
        rec, graph, geo = b.record, b.graph, b.record.geometry
        bank = fold_banks[rec.shape_family]
        mapper = Mapper(bundles, registry, bank)

        curves = {
            c.name: {"poly": _round_poly(c.polyline_local), "runtime_id": c.runtime_id}
            for c in geo.curves.values()
        }
        points = {p.name: [round(p.uv_local[0], 2), round(p.uv_local[1], 2)]
                  for p in geo.points.values()}
        cells = [{
            "id": c.cell_id, "polygon": _round_poly(c.polygon), "area": round(c.area, 1),
            "centroid": [round(c.centroid[0], 2), round(c.centroid[1], 2)],
            "curves": c.curve_names, "points": c.point_names,
        } for c in graph.cells]
        subcells = [{
            "id": s.subcell_id, "parent": s.parent_cell, "polygon": _round_poly(s.polygon),
            "area": round(s.area, 1),
            "centroid": [round(s.centroid[0], 2), round(s.centroid[1], 2)],
            "curves": s.curve_names, "points": s.point_names,
            "waist_ratio": round(s.waist_ratio, 3),
        } for s in graph.subcells]

        silver = [{
            "region": t.region_name, "label_id": t.label_id, "function": t.function,
            "entity_type": t.entity_type, "curves": t.curve_names, "faces": t.face_ids,
            "points": t.point_names, "ordinal": t.ordinal,
            "flags": t.flags, "score": round(t.match_score, 3),
        } for t in b.silver]

        predictions = {}
        for profile in registry.profiles:
            r = mapper.map_query(rec.section_id, label_id=profile.label_id, top_k=60)
            if r["decision"] == "unsupported":
                continue
            predictions[profile.short] = {
                "label_id": profile.label_id,
                "entity_type": r["entity_type"],
                "scorer": r["scorer"],
                "decision": r["decision"],
                "confidence": r["confidence"],
                "evidence": r["evidence"],
                "instances": [
                    {
                        "score": inst["score"],
                        "entity_type": inst["entity_type"],
                        "curves": inst["curves"], "faces": inst["faces"],
                        "points": inst["points"],
                    }
                    for inst in r["instances"]
                ],
                "candidates": [[c["name"], c["score"]] for c in r["candidates_topk"][:30]],
            }

        sections_out.append({
            "section_id": rec.section_id,
            "family": rec.shape_family,
            "topology": rec.topology,
            "source": geo.source,
            "plane": geo.plane,
            "width": round(geo.width, 2),
            "height": round(geo.height, 2),
            "n_points": len(points), "n_curves": len(curves),
            "points": points, "curves": curves,
            "cells": cells, "subcells": subcells,
            "silver": silver,
            "predictions": predictions,
            "notes": (rec.meta.get("shape") or {}).get("notes") or "",
        })

    data = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "note": "预测由留出该截面形状族的模型给出（与交叉验证一致，无泄漏）",
        "metrics": metrics_summary or {},
        "labels": [{
            "label_id": p.label_id, "short": p.short, "caption_zh": p.caption_zh,
            "caption_en": p.caption_en, "entity_type": p.entity_type, "aliases": p.aliases,
        } for p in registry.profiles],
        "position_words": registry.position_words,
        "ordinal_words": {str(k): v for k, v in registry.ordinal_words.items()},
        "sections": sections_out,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    js = "window.VIEWER_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n"
    out_path.write_text(js, encoding="utf-8")
    return out_path
