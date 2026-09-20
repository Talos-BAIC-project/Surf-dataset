"""几何解析层测试：DFC 脚本与 XML 双源、平面检测、局部坐标。"""

import pytest

from tools.Brep2Regin.label2brep.config import SECTIONS_DIR
from tools.Brep2Regin.label2brep.dataset import load_all_sections, load_section_record

pytestmark = pytest.mark.skipif(not SECTIONS_DIR.exists(), reason="dfc-dataset 不存在")


def test_mu_shape_1_from_script():
    rec = load_section_record(SECTIONS_DIR / "mu-shape-1")
    geo = rec.geometry
    assert geo.source == "py"
    assert geo.plane == "YZ"
    assert len(geo.points) == 16
    assert len(geo.curves) == 18
    assert geo.width == pytest.approx(39.0, abs=0.1)
    assert geo.height == pytest.approx(105.0, abs=0.1)
    # 局部坐标以 bbox 左下角为原点
    assert min(p.uv_local[0] for p in geo.points.values()) == pytest.approx(0.0, abs=1e-6)
    assert min(p.uv_local[1] for p in geo.points.values()) == pytest.approx(0.0, abs=1e-6)


def test_u_shape_1_from_xml():
    rec = load_section_record(SECTIONS_DIR / "U-shape-1")
    geo = rec.geometry
    assert geo.source == "xml"
    assert len(geo.curves) == 7
    assert geo.width == pytest.approx(86.6, abs=0.1)
    assert geo.height == pytest.approx(87.5, abs=0.1)


def test_all_sections_load_and_match_yaml_bbox():
    records = load_all_sections()
    assert len(records) == 27
    mismatches = []
    for rec in records:
        yw, yh = rec.yaml_bbox
        if yw == 0 and yh == 0:
            continue
        g = rec.geometry
        if abs(g.width - yw) > 0.6 or abs(g.height - yh) > 0.6:
            mismatches.append(rec.section_id)
    # 已知例外：B-shape-6 的 yaml 高度笔误；一-shape-1 的 yaml 记录的是绝对坐标
    assert set(mismatches) <= {"B-shape-6", "一-shape-1"}


def test_xy_plane_annotation_frame():
    """ji-shape-1 位于 XY 平面，标注竖轴 v = x_max - x（实测对齐）。"""
    rec = load_section_record(SECTIONS_DIR / "ji-shape-1")
    geo = rec.geometry
    assert geo.plane == "XY"
    assert geo.width == pytest.approx(86.3, abs=0.1)
    assert geo.height == pytest.approx(258.2, abs=0.1)
