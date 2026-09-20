"""数据扩增（T1–T5）测试：各操作的几何/标签不变量、校验门、确定性、持久化、评估接入。"""

import random

import pytest

from tools.Brep2Regin.label2brep.augment import (SourceInfo, _Work, feature_sensitivity, fingerprint, generate_variants,
                                load_aug_bundles, make_variant, op_rib, save_variants,
                                select_pilot_bundles, source_sha256)
from tools.Brep2Regin.label2brep.config import SECTIONS_DIR
from tools.Brep2Regin.label2brep.evaluate import evaluate_lofo_with_aug, source_weights, summarize
from tools.Brep2Regin.label2brep.geometry import build_section_geometry
from tools.Brep2Regin.label2brep.graph import build_section_graph
from tools.Brep2Regin.label2brep.pipeline import build_corpus

pytestmark = pytest.mark.skipif(not SECTIONS_DIR.exists(), reason="dfc-dataset 不存在")


@pytest.fixture(scope="module")
def corpus():
    bundles, registry = build_corpus()
    return bundles, registry, {b.record.section_id: b for b in bundles}


def _variant(by_id, registry, sid, ops, seed):
    src = by_id[sid]
    var, reason = make_variant(src, registry, random.Random(seed), ops, f"{sid}@t", {fingerprint(src.graph.geo)},
                               SourceInfo.of(src))
    return src, var, reason


def _n_targets(targets):
    return sum(1 for t in targets if not t.is_empty and "synthetic" not in t.flags)


def test_split_keeps_topology_length_and_labels(corpus):
    _, registry, by_id = corpus
    src, var, reason = _variant(by_id, registry, "mu-shape-1", ["split"], 11)
    assert var is not None, reason
    assert len(var.graph.cells) == 3
    assert len(var.geometry.curves) > len(src.graph.geo.curves)
    total_src = sum(c.length for c in src.graph.geo.curves.values())
    total_var = sum(c.length for c in var.geometry.curves.values())
    assert abs(total_src - total_var) < 1e-6
    assert set(var.work.name_map) == set(src.graph.geo.curves)
    assert all(var.work.name_map[c] for c in src.graph.geo.curves)
    assert _n_targets(var.silver) == _n_targets(src.silver)
    # 子段继承父曲线标签：每条源筋映射出的子段集合，恰好是变体中某个 internal_web 目标
    src_by_name = {t.region_name: t for t in src.silver}
    for name in ("stiffener_a", "stiffener_b"):
        expected = {n for c in src_by_name[name].curve_names for n in var.work.name_map[c]}
        assert any(set(t.curve_names) == expected for t in var.silver if t.label_id.endswith(".internal_web"))


def test_affine_ops_agree_with_bbox_matching(corpus):
    """T2/T5 单操作：传播标签与仿射后重跑 bbox 匹配一致；对称截面的镜像与源重复属正常拒绝。"""
    bundles, registry, by_id = corpus
    agreements, accepted, tried = [], 0, 0
    for b in bundles:
        if not b.record.regions or not _n_targets(b.silver):
            continue
        for kind, seed in (("scale", 3), ("rigid", 5)):
            _, var, reason = _variant(by_id, registry, b.record.section_id, [kind], seed)
            if var is None and reason == "gate5_duplicate":
                continue
            tried += 1
            if var is None:
                continue
            accepted += 1
            if var.info.get("affine_agreement") is not None:
                agreements.append(var.info["affine_agreement"])
    assert accepted / tried >= 0.9
    assert agreements and min(agreements) >= 0.95


def test_rigid_plane_change_roundtrips_through_loader(corpus):
    _, registry, by_id = corpus
    src = by_id["mu-shape-1"]
    work = _Work(src.graph.geo)
    from tools.Brep2Regin.label2brep.augment import op_rigid
    op_rigid(work, random.Random(1), None, kind="rot90", plane="XY")
    geo = work.to_geometry("rt")
    raw = {"name": geo.section_name,
           "points": {p.name: p.xyz for p in geo.points.values()},
           "curves": [(c.name, c.start, c.end) for c in geo.curves.values()]}
    reparsed = build_section_geometry("rt", raw, "aug")
    assert reparsed.plane == "XY"
    for name, p in geo.points.items():
        q = reparsed.points[name]
        assert abs(p.uv_local[0] - q.uv_local[0]) < 1e-6 and abs(p.uv_local[1] - q.uv_local[1]) < 1e-6


def test_move_keeps_topology_and_changes_geometry(corpus):
    _, registry, by_id = corpus
    src, var, reason = _variant(by_id, registry, "kou-shape-1", ["move"], 2)
    assert var is not None, reason
    assert len(var.graph.cells) == len(src.graph.cells)
    assert len(var.geometry.curves) == len(src.graph.geo.curves)
    assert (abs(var.geometry.width - src.graph.geo.width) > 0.5 or
            abs(var.geometry.height - src.graph.geo.height) > 0.5)
    assert _n_targets(var.silver) == _n_targets(src.silver)


def test_rib_add_and_delete(corpus):
    _, registry, by_id = corpus
    src = by_id["mu-shape-1"]
    # 加筋：cell +1，新增一条 internal_web 目标，腔体按定义重派生
    var = None
    for seed in range(20):
        _, var, _ = _variant(by_id, registry, "mu-shape-1", ["rib"], seed)
        if var is not None and var.ops[0]["params"]["mode"] == "add":
            break
    assert var is not None and var.ops[0]["params"]["mode"] == "add"
    assert len(var.graph.cells) == 4
    chambers = [t for t in var.silver if t.label_id.endswith(".chamber")]
    assert len(chambers) == 4 and all("aug_rederived" in t.flags for t in chambers)
    added = [t for t in var.silver if "aug_added" in t.flags]
    assert len(added) == 1 and added[0].label_id.endswith(".internal_web")
    # 删筋：直接调用 op，cell -1
    work = _Work(src.graph.geo)
    params = op_rib(work, random.Random(0), src.graph, mode="delete")
    assert params["mode"] == "delete" and params["expected_cell_delta"] == -1
    g = build_section_graph(work.to_geometry("del"))
    assert len(g.cells) == 2


def test_generate_is_deterministic_and_gated(corpus):
    bundles, registry, _ = corpus
    v1, r1 = generate_variants(bundles, registry, per_section=2, seed=7, quota=0)
    v2, _ = generate_variants(bundles, registry, per_section=2, seed=7, quota=0)
    assert [v.variant_id for v in v1] == [v.variant_id for v in v2]
    assert [v.info["fingerprint"] for v in v1] == [v.info["fingerprint"] for v in v2]
    assert len(v1) >= 0.8 * 2 * r1["sections_eligible"]
    for v in v1:
        for t in v.silver:
            if "synthetic" in t.flags or "aug_removed" in t.flags:
                continue
            assert not t.is_empty, (v.variant_id, t.region_name)
        assert v.family in {b.record.shape_family for b in bundles}


def test_save_load_roundtrip(corpus, tmp_path):
    bundles, registry, _ = corpus
    variants, _ = generate_variants(bundles[:6], registry, per_section=2, seed=3, quota=0)
    path = save_variants(variants, tmp_path / "aug.jsonl")
    loaded = load_aug_bundles(path, registry)
    assert [b.record.section_id for b in loaded] == [v.variant_id for v in variants]
    for v, b in zip(variants, loaded):
        assert len(b.graph.cells) == len(v.graph.cells)
        assert {t.region_name: tuple(t.curve_names) for t in b.silver} == \
               {t.region_name: tuple(t.curve_names) for t in v.silver}
        assert b.record.meta["aug"]["source_id"] == v.source_id
        assert b.record.meta["aug"]["source_sha256"] == v.source_sha256
        assert b.record.meta["aug"]["seed"] == 3
        assert b.samples  # 变体能生成训练样本


def test_variant_record_has_reproducible_provenance(corpus):
    bundles, registry, by_id = corpus
    selected = select_pilot_bundles(bundles)
    assert len(selected) == 5
    assert {b.record.section_id for b in selected} >= {"U-shape-1", "mu-shape-1"}
    assert len({b.record.shape_family for b in selected}) == 5
    variants, _ = generate_variants(selected, registry, per_section=1, seed=42, quota=0)
    assert len(variants) == 5
    for v in variants:
        row = v.to_record()
        required = {"source_id", "variant_id", "shape_family", "ops", "seed", "name_map",
                    "geometry", "propagated_labels", "validation_report", "source_sha256"}
        assert required <= row.keys()
        assert row["seed"] == 42
        assert row["source_sha256"] == source_sha256(by_id[v.source_id])
        assert len(row["source_sha256"]) == 64
        assert row["source_manifest"] and all(len(x["sha256"]) == 64 for x in row["source_manifest"])
        assert row["shape_family"] == by_id[v.source_id].record.shape_family
        assert row["propagated_labels"]
        assert row["validation_report"]["passed"] is True
        assert len(row["validation_report"]["gates"]) == 6
        assert all(g["passed"] for g in row["validation_report"]["gates"].values())


def test_lofo_with_aug_isolates_families_and_reports(corpus, tmp_path):
    bundles, registry, _ = corpus
    variants, _ = generate_variants(bundles, registry, per_section=1, seed=9, quota=0)
    aug = load_aug_bundles(save_variants(variants, tmp_path / "a.jsonl"), registry)
    # 源权重：同源的原始 + 变体合计为 1
    w = source_weights(bundles, aug)
    by_src = {}
    for b in aug:
        by_src.setdefault(b.record.meta["aug"]["source_id"], []).append(b.record.section_id)
    for src, vids in by_src.items():
        assert abs(w[src] + sum(w[v] for v in vids) - 1.0) < 1e-9
    rows, inv = evaluate_lofo_with_aug(bundles, registry, aug)
    assert {r.split for r in rows} == {"orig", "aug"}
    assert inv and all(0.0 <= r.consistency <= 1.0 for r in inv)
    summary = summarize(rows, inv)
    assert "aug_test" in summary and "invariance" in summary
    # 主表口径不变：只统计原始截面
    assert summary["overall"]["hybrid"]["n"] == sum(1 for r in rows if r.split == "orig" and r.scorer == "hybrid")


def test_feature_audit_has_no_unstable_features(corpus):
    bundles, _, _ = corpus
    _, info = feature_sensitivity(bundles, seed=1)
    assert info["sections"] >= 20
    assert info["unstable"] == []
