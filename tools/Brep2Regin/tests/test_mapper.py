"""端到端 Mapper 测试：全量训练模型上的行为契约。"""

import pytest

from tools.Brep2Regin.label2brep.config import SECTIONS_DIR
from tools.Brep2Regin.label2brep.evaluate import train_full
from tools.Brep2Regin.label2brep.mapper import Mapper
from tools.Brep2Regin.label2brep.models import HybridBank
from tools.Brep2Regin.label2brep.pipeline import build_corpus

pytestmark = pytest.mark.skipif(not SECTIONS_DIR.exists(), reason="dfc-dataset 不存在")


@pytest.fixture(scope="module")
def mapper():
    bundles, registry = build_corpus()
    lr = train_full(bundles)
    bank = HybridBank()
    bank.curve_models = lr.curve_models
    bank.face_model = lr.face_model
    return Mapper(bundles, registry, bank)


def _target_names(result, entity_type=None):
    return [t["name"] for t in result["targets"]
            if entity_type is None or t["entity_type"] == entity_type]


def test_stiffener_query(mapper):
    r = mapper.map_query("mu-shape-1", query="加强筋")
    assert r["decision"] == "resolved"
    assert set(_target_names(r)) == {"S_1_SL_17", "S_1_SL_18"}
    assert r["latency_ms"] < 50


def test_center_two_beams(mapper):
    r = mapper.map_query("mu-shape-1", query="中间两道筋")
    assert set(_target_names(r)) == {"S_1_SL_17", "S_1_SL_18"}


def test_chamber_ordinal(mapper):
    r = mapper.map_query("mu-shape-1", query="chamber_2")
    assert _target_names(r, "face") == ["cell_2"]
    assert r["decision"] == "resolved"
    # 面实例的边界曲线是派生高亮
    assert "S_1_SL_17" in r["derived_curves"]


def test_b_shape_double_chamber(mapper):
    r = mapper.map_query("B-shape-2", query="腔体")
    assert set(_target_names(r, "face")) == {"cell_1#0", "cell_1#1"}


def test_outer_contour(mapper):
    r = mapper.map_query("mu-shape-1", query="外轮廓")
    names = set(_target_names(r))
    assert "S_1_SL_1" not in names        # 悬挂法兰不属于外轮廓
    assert {"S_1_SL_2", "S_1_SL_4"} <= names


def test_chamber_on_open_section_unsupported(mapper):
    r = mapper.map_query("ji-shape-1", query="腔体")
    assert r["decision"] in ("unsupported", "not_found")


def test_unresolvable_query(mapper):
    r = mapper.map_query("mu-shape-1", query="完全无关的文本xyz")
    assert r["decision"] == "unsupported"
    assert r["targets"] == []


def test_ordinal_out_of_range(mapper):
    r = mapper.map_query("mu-shape-1", query="chamber_9")
    assert r["decision"] == "not_found"


def test_output_contract_fields(mapper):
    r = mapper.map_query("mu-shape-1", query="腔体")
    for key in ["query", "label_id", "section_id", "decision", "confidence",
                "targets", "instances", "candidates_topk", "evidence", "latency_ms",
                "selector", "derived_points", "derived_curves"]:
        assert key in r
    for t in r["targets"]:
        assert t["stable_ref"].startswith("mu-shape-1/")
