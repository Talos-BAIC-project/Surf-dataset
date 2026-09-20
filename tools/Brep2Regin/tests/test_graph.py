"""属性图测试：cell 检测、桥接、子腔、拓扑角色。"""

import pytest

from tools.Brep2Regin.label2brep.config import SECTIONS_DIR
from tools.Brep2Regin.label2brep.dataset import load_all_sections, load_section_record
from tools.Brep2Regin.label2brep.graph import build_section_graph

pytestmark = pytest.mark.skipif(not SECTIONS_DIR.exists(), reason="dfc-dataset 不存在")


def _graph(section_id):
    rec = load_section_record(SECTIONS_DIR / section_id)
    return rec, build_section_graph(rec.geometry)


def test_mu_shape_1_cells_and_roles():
    rec, g = _graph("mu-shape-1")
    assert len(g.cells) == 3                        # 目字形三腔
    # cell 自上而下编号
    assert g.cells[0].centroid[1] > g.cells[1].centroid[1] > g.cells[2].centroid[1]
    # 两条筋分隔相邻腔
    separators = [c for c, t in g.curve_topo.items() if t.n_cells == 2]
    assert set(separators) == {"S_1_SL_17", "S_1_SL_18"}
    # 两个悬挂法兰
    dangling = [c for c, t in g.curve_topo.items() if t.dangling]
    assert set(dangling) == {"S_1_SL_1", "S_1_SL_9"}
    # 倒角：2 外（凸）+ 4 内
    trans = {c: t for c, t in g.curve_topo.items() if t.transition_like}
    convex = {c for c, t in trans.items() if t.transition_convex}
    assert convex == {"S_1_SL_3", "S_1_SL_7"}
    assert len(trans) - len(convex) == 4


def test_b_shape_subcells():
    """B 字形：拓扑 1 个 cell，深凹槽腰线切出 2 个虚拟子腔。"""
    rec, g = _graph("B-shape-2")
    assert len(g.cells) == 1
    assert len(g.subcells) == 2
    assert {s.parent_cell for s in g.subcells} == {"cell_1"}
    assert all(s.waist_ratio < 0.6 for s in g.subcells)


def test_ri_shape_6_bridging():
    """日字形筋带与壁体不共享端点：共线缺口桥接后恢复 2 个腔。"""
    rec, g = _graph("ri-shape-6")
    bridges = [e for e in g.edges if e.orig_curve.startswith("__bridge_")]
    assert len(bridges) >= 1
    assert len(g.cells) == 2


def test_cells_match_yaml_chamber_count():
    for rec in load_all_sections():
        g = build_section_graph(rec.geometry)
        fs = rec.feature_statistics
        yaml_ch = fs.get("chamber_count")
        if yaml_ch is None:
            yaml_ch = (rec.meta.get("shape") or {}).get("n_chambers")
        if yaml_ch is None:
            continue
        big = sum(1 for c in g.cells if c.area > 0.15 * max(cc.area for cc in g.cells)) if g.cells else 0
        ok = big == yaml_ch or len(g.subcells) == yaml_ch
        assert ok, f"{rec.section_id}: cells={len(g.cells)} sub={len(g.subcells)} yaml={yaml_ch}"


def test_open_sections_have_no_cells():
    for sid in ["ji-shape-1", "m-shape-3", "一-shape-1"]:
        rec, g = _graph(sid)
        assert len(g.cells) == 0
        assert not g.is_closed
