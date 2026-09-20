"""silver 金标引导测试。"""

import pytest

from tools.Brep2Regin.label2brep.config import SECTIONS_DIR
from tools.Brep2Regin.label2brep.dataset import load_section_record
from tools.Brep2Regin.label2brep.graph import build_section_graph
from tools.Brep2Regin.label2brep.labels import LabelRegistry
from tools.Brep2Regin.label2brep.pipeline import build_corpus
from tools.Brep2Regin.label2brep.silver import build_silver_targets

pytestmark = pytest.mark.skipif(not SECTIONS_DIR.exists(), reason="dfc-dataset 不存在")


def _targets(section_id):
    rec = load_section_record(SECTIONS_DIR / section_id)
    graph = build_section_graph(rec.geometry)
    registry = LabelRegistry.load()
    return {t.region_name: t for t in build_silver_targets(rec, graph, registry)}


def test_mu_shape_1_silver():
    t = _targets("mu-shape-1")
    assert t["stiffener_a"].curve_names == ["S_1_SL_17"]
    assert t["stiffener_b"].curve_names == ["S_1_SL_18"]
    assert t["flange_a"].curve_names == ["S_1_SL_1"]
    assert set(t["notch"].curve_names) == {"S_1_SL_11", "S_1_SL_12", "S_1_SL_13",
                                           "S_1_SL_14", "S_1_SL_15"}
    assert t["chamber_1"].face_ids == ["cell_1"]
    assert t["chamber_2"].face_ids == ["cell_2"]
    assert t["chamber_3"].face_ids == ["cell_3"]
    assert set(t["fillet_outer"].curve_names) == {"S_1_SL_3", "S_1_SL_7"}
    assert set(t["fillet_inner"].curve_names) == {"S_1_SL_11", "S_1_SL_12",
                                                  "S_1_SL_14", "S_1_SL_15"}
    assert t["outer_contour"].curve_names  # 合成外轮廓金标非空


def test_b_shape_chambers_map_to_subcells():
    t = _targets("B-shape-2")
    assert t["chamber_1"].face_ids == ["cell_1#0"]
    assert t["chamber_2"].face_ids == ["cell_1#1"]


def test_chamfer_corner_point_fallback():
    """ji-shape-3 的倒角在 DFC 中被简化为尖角 -> 点实体金标。"""
    t = _targets("ji-shape-3")
    point_targets = [x for x in t.values() if x.entity_type == "point"]
    assert len(point_targets) >= 2
    assert all(x.point_names for x in point_targets)


def test_silver_coverage():
    bundles, _ = build_corpus()
    total = ok = 0
    for b in bundles:
        for t in b.silver:
            if "synthetic" in t.flags:
                continue
            total += 1
            if not t.is_empty:
                ok += 1
    assert total == 132
    assert ok >= 131      # 唯一例外：ji-shape-3 wall_b 是数据集标注错误
