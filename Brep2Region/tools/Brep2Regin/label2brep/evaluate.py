"""评估 harness：按形状族留一交叉验证（LOFO），规则基线 vs 逻辑回归。

同形状族的参数化变体高度相似，随机切分会数据泄漏；
按形状族分组保证测试截面的"形状家族"从未在训练中出现。

带扩增数据时（`aug_bundles`）：变体继承源截面的形状族，只进训练折；
留出族的变体构成 `aug` 测试集（split="aug"），并计算源截面与变体之间
逐实体概率的一致性（不变性指标）。
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .labels import LabelRegistry, Selector
from .mapper import Mapper
from .models import HybridBank, ModelBank, RulesBank
from .pipeline import SectionBundle
from .samples import QuerySample


@dataclass
class EvalRow:
    scorer: str
    family: str
    section_id: str
    label_id: str
    kind: str
    entity_type: str
    n_gold: int
    n_pred: int
    precision: float
    recall: float
    f1: float
    jaccard: float
    exact: int
    cand_recall_at3: float | None
    cand_recall_at20: float | None
    decision: str
    confidence: float
    latency_ms: float
    split: str = "orig"          # orig | aug（留出族的扩增变体）
    ops: str = ""                # 变体的操作签名，如 "scale+split"


@dataclass
class InvRow:
    """源截面与其变体之间的逐实体概率一致性（1 - 平均绝对差）。"""
    scorer: str
    family: str
    source_id: str
    variant_id: str
    ops: str
    label_id: str
    entity_type: str
    n_pairs: int
    consistency: float


def _typed_set(entity_type_default: str, curves: list[str], faces: list[str],
               points: list[str]) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    out.update(("curve", c) for c in curves)
    out.update(("face", f) for f in faces)
    out.update(("point", p) for p in points)
    return out


def _gold_set(sample: QuerySample) -> set[tuple[str, str]]:
    if sample.entity_type == "face":
        return {("face", f) for f in sample.target_faces}
    if sample.entity_type == "point":
        # 混合类型样本（如倒角=角点+过渡曲线）：主类型为点时仍保留曲线目标
        out = {("point", p) for p in sample.target_points}
        out.update(("curve", c) for c in sample.target_curves)
        return out
    return {("curve", c) for c in sample.target_curves}


def _pred_set(result: dict) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for t in result["targets"]:
        if t["entity_type"] == "face":
            out.add(("face", t["name"]))
        elif t["entity_type"] == "point":
            out.add(("point", t["name"]))
        else:
            out.add(("curve", t["name"]))
    return out


def evaluate_sample(mapper: Mapper, sample: QuerySample, scorer_name: str,
                    split: str = "orig", ops: str = "") -> EvalRow:
    selector = Selector(ordinal=sample.ordinal) if sample.kind == "specific" else Selector()
    result = mapper.map_query(sample.section_id, label_id=sample.label_id, selector=selector,
                              top_k=100)
    gold = _gold_set(sample)
    pred = _pred_set(result)
    inter = len(gold & pred)
    p = inter / len(pred) if pred else 0.0
    r = inter / len(gold) if gold else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    union = len(gold | pred)
    jac = inter / union if union else 0.0

    # 候选召回（排序层质量，不受 selector 影响）：仅在类型一致时计算
    cand3 = cand20 = None
    cand_type = "face" if sample.entity_type == "face" else "curve"
    gold_same = {name for t, name in gold if t == cand_type}
    if gold_same:
        ranked = [c["name"] for c in result["candidates_topk"]]
        cand3 = len(gold_same & set(ranked[:3])) / len(gold_same)
        cand20 = len(gold_same & set(ranked[:20])) / len(gold_same)

    return EvalRow(
        scorer=scorer_name, family=sample.family, section_id=sample.section_id,
        label_id=sample.label_id, kind=sample.kind, entity_type=sample.entity_type,
        n_gold=len(gold), n_pred=len(pred),
        precision=round(p, 4), recall=round(r, 4), f1=round(f1, 4), jaccard=round(jac, 4),
        exact=int(gold == pred), cand_recall_at3=cand3, cand_recall_at20=cand20,
        decision=result["decision"], confidence=result["confidence"],
        latency_ms=result["latency_ms"], split=split, ops=ops,
    )


def _aug_meta(b: SectionBundle) -> dict:
    return b.record.meta.get("aug") or {}


def _ops_signature(b: SectionBundle) -> str:
    return "+".join(o["kind"] for o in _aug_meta(b).get("ops", []))


def source_weights(train: list[SectionBundle], train_aug: list[SectionBundle]) -> dict[str, float]:
    """同一源截面的原始 + 变体共享权重 1：每行权重 = 1 / (1 + 该源的变体数)。"""
    n_var: dict[str, int] = {}
    for v in train_aug:
        src = _aug_meta(v).get("source_id", v.record.section_id)
        n_var[src] = n_var.get(src, 0) + 1
    weights: dict[str, float] = {}
    for b in train:
        weights[b.record.section_id] = 1.0 / (1 + n_var.get(b.record.section_id, 0))
    for v in train_aug:
        src = _aug_meta(v).get("source_id", v.record.section_id)
        weights[v.record.section_id] = 1.0 / (1 + n_var.get(src, 0))
    return weights


def invariance_rows(bank, scorer_name: str, source: SectionBundle, variant: SectionBundle,
                    registry: LabelRegistry) -> list[InvRow]:
    """源截面 vs 变体：同一实体（经 name_map / cell_map 对应）在同一标签下的概率差。"""
    meta = _aug_meta(variant)
    name_map: dict[str, list[str]] = meta.get("name_map") or {}
    cell_map: dict[str, str | None] = meta.get("cell_map") or {}
    labels = sorted({s.label_id for s in source.samples if s.kind == "generic"})
    fs, fv = source.features, variant.features
    idx_s = {n: i for i, n in enumerate(fs.curve_names)}
    idx_v = {n: i for i, n in enumerate(fv.curve_names)}
    out: list[InvRow] = []
    for label_id in labels:
        profile = registry.by_id.get(label_id)
        if profile is None:
            continue
        pairs: list[tuple[float, float]] = []
        if profile.entity_type == "face":
            if not cell_map or not fs.face_ids or not fv.face_ids:
                continue
            ps, _ = bank.score_faces(fs)
            pv, _ = bank.score_faces(fv)
            fid_s = {f: i for i, f in enumerate(fs.face_ids)}
            fid_v = {f: i for i, f in enumerate(fv.face_ids)}
            for f, m in cell_map.items():
                if m and f in fid_s and m in fid_v:
                    pairs.append((float(ps[fid_s[f]]), float(pv[fid_v[m]])))
        else:
            ps, _ = bank.score_curves(profile.short, fs)
            pv, _ = bank.score_curves(profile.short, fv)
            for c, children in name_map.items():
                if c not in idx_s:
                    continue
                kids = [float(pv[idx_v[k]]) for k in children if k in idx_v]
                if kids:
                    pairs.append((float(ps[idx_s[c]]), float(np.mean(kids))))
        if pairs:
            diff = float(np.mean([abs(a - b) for a, b in pairs]))
            out.append(InvRow(scorer=scorer_name, family=source.record.shape_family,
                              source_id=source.record.section_id, variant_id=variant.record.section_id,
                              ops=_ops_signature(variant), label_id=label_id,
                              entity_type=profile.entity_type, n_pairs=len(pairs),
                              consistency=round(1.0 - diff, 4)))
    return out


def evaluate_lofo_with_aug(bundles: list[SectionBundle], registry: LabelRegistry,
                           aug_bundles: list[SectionBundle] | None = None
                           ) -> tuple[list[EvalRow], list[InvRow]]:
    """LOFO：训练 = 非留出族的原始截面 + 其变体；主测试 = 留出族原始截面；
    次测试（split=aug）= 留出族的变体；并计算不变性。"""
    aug_bundles = aug_bundles or []
    by_id = {b.record.section_id: b for b in bundles}
    fams = sorted({b.record.shape_family for b in bundles})
    rows: list[EvalRow] = []
    inv: list[InvRow] = []
    for fam in fams:
        train = [b for b in bundles if b.record.shape_family != fam]
        train_aug = [b for b in aug_bundles if b.record.shape_family != fam]
        test = [b for b in bundles if b.record.shape_family == fam]
        test_aug = [b for b in aug_bundles if b.record.shape_family == fam]
        test_samples = [s for b in test for s in b.samples]
        if not test_samples:
            continue
        train_all = train + train_aug
        train_samples = [s for b in train_all for s in b.samples if s.kind == "generic"]
        bank_lr = ModelBank()
        bank_lr.train(train_all, train_samples, source_weights(train, train_aug) if train_aug else None)
        bank_hybrid = HybridBank()
        bank_hybrid.curve_models = bank_lr.curve_models
        bank_hybrid.face_model = bank_lr.face_model
        banks = {"rules": RulesBank(), "logreg": bank_lr, "hybrid": bank_hybrid}
        for scorer_name, bank in banks.items():
            mapper = Mapper(bundles + aug_bundles, registry, bank)
            for s in test_samples:
                rows.append(evaluate_sample(mapper, s, scorer_name))
            for v in test_aug:
                sig = _ops_signature(v)
                for s in v.samples:
                    rows.append(evaluate_sample(mapper, s, scorer_name, split="aug", ops=sig))
                src = by_id.get(_aug_meta(v).get("source_id", ""))
                if src is not None:
                    inv.extend(invariance_rows(bank, scorer_name, src, v, registry))
    return rows, inv


def evaluate_lofo(bundles: list[SectionBundle], registry: LabelRegistry,
                  aug_bundles: list[SectionBundle] | None = None) -> list[EvalRow]:
    rows, _ = evaluate_lofo_with_aug(bundles, registry, aug_bundles)
    return rows


def train_full(bundles: list[SectionBundle], aug_bundles: list[SectionBundle] | None = None) -> ModelBank:
    aug_bundles = list(aug_bundles or [])
    all_bundles = bundles + aug_bundles
    samples = [s for b in all_bundles for s in b.samples if s.kind == "generic"]
    bank = ModelBank()
    bank.train(all_bundles, samples, source_weights(bundles, aug_bundles) if aug_bundles else None)
    return bank


# ---------------------------------------------------------------------------
# 汇总报告
# ---------------------------------------------------------------------------

def _mean(vals: list[float]) -> float:
    return round(statistics.fmean(vals), 4) if vals else 0.0


def _agg(rows: list[EvalRow]) -> dict:
    return {
        "n": len(rows),
        "precision": _mean([r.precision for r in rows]),
        "recall": _mean([r.recall for r in rows]),
        "f1": _mean([r.f1 for r in rows]),
        "jaccard": _mean([r.jaccard for r in rows]),
        "exact_acc": _mean([float(r.exact) for r in rows]),
        "cand_recall@3": _mean([r.cand_recall_at3 for r in rows if r.cand_recall_at3 is not None]),
        "cand_recall@20": _mean([r.cand_recall_at20 for r in rows if r.cand_recall_at20 is not None]),
    }


def summarize(rows: list[EvalRow], inv_rows: list[InvRow] | None = None) -> dict:
    """主表只统计 split=orig 的行（与无扩增时口径一致）；扩增测试集与不变性另列。"""
    aug_rows = [r for r in rows if r.split == "aug"]
    rows = [r for r in rows if r.split != "aug"]
    out: dict = {"overall": {}, "by_label": {}, "by_family": {}, "by_kind": {},
                 "by_entity_type": {}, "latency": {}, "decisions": {}}
    scorers = sorted({r.scorer for r in rows})
    if aug_rows:
        out["aug_test"] = {"overall": {}, "by_ops": {}, "by_label": {}}
        for sc in sorted({r.scorer for r in aug_rows}):
            sub = [r for r in aug_rows if r.scorer == sc]
            out["aug_test"]["overall"][sc] = _agg(sub)
            for key, attr in (("by_ops", "ops"), ("by_label", "label_id")):
                for val in sorted({getattr(r, attr) for r in sub}):
                    out["aug_test"][key].setdefault(val, {})[sc] = _agg([r for r in sub if getattr(r, attr) == val])
    if inv_rows:
        out["invariance"] = {"overall": {}, "by_ops": {}, "by_label": {}}
        for sc in sorted({r.scorer for r in inv_rows}):
            sub = [r for r in inv_rows if r.scorer == sc]
            out["invariance"]["overall"][sc] = {"n": len(sub), "consistency": _mean([r.consistency for r in sub])}
            for key, attr in (("by_ops", "ops"), ("by_label", "label_id")):
                for val in sorted({getattr(r, attr) for r in sub}):
                    grp = [r for r in sub if getattr(r, attr) == val]
                    out["invariance"][key].setdefault(val, {})[sc] = {
                        "n": len(grp), "consistency": _mean([r.consistency for r in grp])}
    for sc in scorers:
        sub = [r for r in rows if r.scorer == sc]
        out["overall"][sc] = _agg(sub)
        lat = sorted(r.latency_ms for r in sub)
        out["latency"][sc] = {
            "p50_ms": round(lat[len(lat) // 2], 3) if lat else None,
            "p95_ms": round(lat[int(len(lat) * 0.95) - 1], 3) if lat else None,
        }
        decisions: dict[str, int] = {}
        for r in sub:
            decisions[r.decision] = decisions.get(r.decision, 0) + 1
        out["decisions"][sc] = decisions
        for key, attr in (("by_label", "label_id"), ("by_family", "family"),
                          ("by_kind", "kind"), ("by_entity_type", "entity_type")):
            for val in sorted({getattr(r, attr) for r in sub}):
                out[key].setdefault(val, {})[sc] = _agg([r for r in sub if getattr(r, attr) == val])
    return out


def write_report(rows: list[EvalRow], summary: dict, out_dir: Path,
                 inv_rows: list[InvRow] | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "eval_rows.json").write_text(
        json.dumps([asdict(r) for r in rows], ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "eval_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    if inv_rows:
        (out_dir / "invariance_rows.json").write_text(
            json.dumps([asdict(r) for r in inv_rows], ensure_ascii=False, indent=1), encoding="utf-8")

    lines = ["# Label2B-rep 评估报告（按形状族留一交叉验证）", ""]
    lines.append("训练/测试按 shape_family 分组隔离：测试截面所属形状族从未出现在训练集中。")
    if "aug_test" in summary:
        n_aug = sum(m["n"] for m in summary["aug_test"]["overall"].values()) // max(len(summary["aug_test"]["overall"]), 1)
        lines.append(f"训练集包含扩增变体（T1–T5，继承源截面形状族）；主表仍只统计原始截面，"
                     f"留出族的变体另列为扩增测试集（每系统 {n_aug} 条样本）。")
    lines.append("")
    lines.append("## 总体指标")
    lines.append("")
    lines.append("| scorer | 样本数 | P | R | F1 | Jaccard | 完全匹配 | 候选R@3 | 候选R@20 | P50延迟 | P95延迟 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for sc, m in summary["overall"].items():
        lat = summary["latency"][sc]
        lines.append(
            f"| {sc} | {m['n']} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} | "
            f"{m['jaccard']:.3f} | {m['exact_acc']:.3f} | {m['cand_recall@3']:.3f} | "
            f"{m['cand_recall@20']:.3f} | {lat['p50_ms']}ms | {lat['p95_ms']}ms |")
    lines.append("")
    lines.append("## 决策分布")
    lines.append("")
    for sc, d in summary["decisions"].items():
        lines.append(f"- {sc}: " + ", ".join(f"{k}={v}" for k, v in sorted(d.items())))
    lines.append("")
    for key, title in (("by_label", "按 Label"), ("by_kind", "按查询粒度"),
                       ("by_entity_type", "按实体类型"), ("by_family", "按形状族")):
        lines.append(f"## {title}")
        lines.append("")
        scorers = sorted(summary["overall"])
        header = "| " + title + " | " + " | ".join(f"{sc} F1 (n)" for sc in scorers) + " |"
        lines.append(header)
        lines.append("|---" * (len(scorers) + 1) + "|")
        for val, per in sorted(summary[key].items()):
            cells = []
            for sc in scorers:
                m = per.get(sc)
                cells.append(f"{m['f1']:.3f} ({m['n']})" if m else "-")
            lines.append(f"| {val} | " + " | ".join(cells) + " |")
        lines.append("")

    if "aug_test" in summary:
        aug = summary["aug_test"]
        scorers = sorted(aug["overall"])
        lines.append("## 扩增测试集（留出族的变体）")
        lines.append("")
        lines.append("| scorer | 样本数 | P | R | F1 | 完全匹配 | 候选R@20 |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for sc in scorers:
            m = aug["overall"][sc]
            lines.append(f"| {sc} | {m['n']} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} | "
                         f"{m['exact_acc']:.3f} | {m['cand_recall@20']:.3f} |")
        lines.append("")
        for key, title in (("by_ops", "扩增测试集按操作组合"), ("by_label", "扩增测试集按 Label")):
            lines.append(f"### {title}")
            lines.append("")
            lines.append("| " + title + " | " + " | ".join(f"{sc} F1 (n)" for sc in scorers) + " |")
            lines.append("|---" * (len(scorers) + 1) + "|")
            for val, per in sorted(aug[key].items()):
                cells = [f"{per[sc]['f1']:.3f} ({per[sc]['n']})" if sc in per else "-" for sc in scorers]
                lines.append(f"| {val} | " + " | ".join(cells) + " |")
            lines.append("")

    if "invariance" in summary:
        inv = summary["invariance"]
        scorers = sorted(inv["overall"])
        lines.append("## 不变性：源截面 vs 变体的逐实体概率一致性（1 − 平均绝对差）")
        lines.append("")
        lines.append("同一实体在源截面与变体中的预测概率应一致；T1/T2/T5 为纯不变操作，目标 ≥ 0.9。")
        lines.append("")
        for key, title in (("by_ops", "按操作组合"), ("by_label", "按 Label")):
            lines.append(f"### {title}")
            lines.append("")
            lines.append("| " + title + " | " + " | ".join(f"{sc} 一致性 (n)" for sc in scorers) + " |")
            lines.append("|---" * (len(scorers) + 1) + "|")
            for val, per in sorted(inv[key].items()):
                cells = [f"{per[sc]['consistency']:.3f} ({per[sc]['n']})" if sc in per else "-" for sc in scorers]
                lines.append(f"| {val} | " + " | ".join(cells) + " |")
            lines.append("")
        lines.append("| 总体 | " + " | ".join(
            f"{inv['overall'][sc]['consistency']:.3f} ({inv['overall'][sc]['n']})" for sc in scorers) + " |")
        lines.append("")
    report = out_dir / "eval_report.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    return report
