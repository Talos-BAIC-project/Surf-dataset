"""命令行入口。

用法（在 Label2B-rep 目录下）：
    python -m label2brep build           # 构建语料：silver 金标 + 查询样本 + 质量报告
    python -m label2brep train [--with-aug]        # 全量训练模型 -> artifacts/model_full.json
    python -m label2brep eval [--with-aug]         # 留一形状族交叉验证 -> artifacts/reports/
    python -m label2brep map <section> "<查询>"   # 单条映射（输出 JSON 契约）
    python -m label2brep export-viewer   # 导出前端数据 -> viewer/viewer_data.js
    python -m label2brep augment [--per-section 20 --seed 1 --quota 200]
                                         # 数据扩增 T1–T5 -> artifacts/aug/
    python -m label2brep audit-features  # T1 拆线下的特征敏感度审计 -> artifacts/reports/
    python -m label2brep all             # build + eval + train + export-viewer
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

from .augment import (AUG_DIR, AUG_FILE, augment_report, feature_sensitivity, generate_variants,
                      load_aug_bundles, save_variants, select_pilot_bundles)
from .config import ARTIFACTS_DIR, REPORTS_DIR, VIEWER_DIR
from .evaluate import evaluate_lofo_with_aug, summarize, train_full, write_report
from .mapper import Mapper
from .models import HybridBank, ModelBank
from .pipeline import all_samples, build_corpus
from .samples import save_samples
from .silver import silver_report
from .viewer_export import export_viewer_data


def _stdout_utf8() -> None:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def cmd_build(args) -> None:
    bundles, registry = build_corpus()
    samples = all_samples(bundles)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    save_samples(samples, ARTIFACTS_DIR / "samples.jsonl")
    report = silver_report({b.record.section_id: b.silver for b in bundles})
    (ARTIFACTS_DIR / "silver_report.md").write_text(report, encoding="utf-8")
    n_regions = sum(len(b.record.regions) for b in bundles)
    n_ok = sum(1 for b in bundles for t in b.silver if not t.is_empty and "synthetic" not in t.flags)
    print(f"sections={len(bundles)} regions={n_regions} silver_ok={n_ok} samples={len(samples)}")
    print(f"-> {ARTIFACTS_DIR / 'samples.jsonl'}")
    print(f"-> {ARTIFACTS_DIR / 'silver_report.md'}")


def _load_aug(args, registry):
    if not getattr(args, "with_aug", False):
        return []
    path = Path(args.aug) if getattr(args, "aug", None) else AUG_FILE
    aug = load_aug_bundles(path, registry)
    if not aug:
        print(f"[warn] 未找到扩增数据 {path}，先运行 `python -m label2brep augment`")
    else:
        print(f"扩增变体 {len(aug)} 个 <- {path}")
    return aug


def cmd_train(args) -> None:
    bundles, registry = build_corpus()
    aug = _load_aug(args, registry)
    bank = train_full(bundles, aug)
    out = ARTIFACTS_DIR / "model_full.json"
    bank.save(out)
    print(f"curve_models={sorted(bank.curve_models)} face_model={'yes' if bank.face_model else 'no'}")
    print(f"-> {out}")


def cmd_eval(args) -> None:
    bundles, registry = build_corpus()
    aug = _load_aug(args, registry)
    rows, inv = evaluate_lofo_with_aug(bundles, registry, aug)
    summary = summarize(rows, inv)
    report = write_report(rows, summary, REPORTS_DIR, inv)
    for sc, m in summary["overall"].items():
        print(f"{sc:8s} n={m['n']} P={m['precision']:.3f} R={m['recall']:.3f} "
              f"F1={m['f1']:.3f} exact={m['exact_acc']:.3f} candR@20={m['cand_recall@20']:.3f}")
    if "aug_test" in summary:
        for sc, m in summary["aug_test"]["overall"].items():
            print(f"aug-test {sc:8s} n={m['n']} F1={m['f1']:.3f} exact={m['exact_acc']:.3f}")
    if "invariance" in summary:
        for sc, m in summary["invariance"]["overall"].items():
            print(f"invariance {sc:8s} n={m['n']} consistency={m['consistency']:.3f}")
    print(f"-> {report}")


def cmd_augment(args) -> None:
    bundles, registry = build_corpus()
    if args.pilot:
        bundles = select_pilot_bundles(bundles, limit=5)
    variants, report = generate_variants(bundles, registry, per_section=args.per_section,
                                         seed=args.seed, quota=args.quota)
    out = Path(args.out) if args.out else (AUG_DIR / "pilot" / "aug_sections.jsonl" if args.pilot else AUG_FILE)
    save_variants(variants, out)
    md = augment_report(bundles, variants, report)
    md_path = out.parent / "aug_report.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"sections={report['sections_eligible']} attempts={report['attempts']} variants={len(variants)}")
    print("rejections:", ", ".join(f"{k}={v}" for k, v in sorted(report["rejections"].items(), key=lambda kv: -kv[1])))
    print(f"-> {out}")
    print(f"-> {md_path}")


def cmd_audit_features(args) -> None:
    bundles, _ = build_corpus()
    md, info = feature_sensitivity(bundles, seed=args.seed)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "feature_sensitivity.md"
    out.write_text(md, encoding="utf-8")
    print(f"sections={info['sections']} unstable={info['unstable']}")
    print(f"-> {out}")


def cmd_map(args) -> None:
    bundles, registry = build_corpus()
    model_path = ARTIFACTS_DIR / "model_full.json"
    if model_path.exists():
        lr = ModelBank.load(model_path)
    else:
        lr = train_full(bundles)
    bank = HybridBank()
    bank.curve_models = lr.curve_models
    bank.face_model = lr.face_model
    mapper = Mapper(bundles, registry, bank)
    result = mapper.map_query(args.section, query=args.query)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_export_viewer(args) -> None:
    bundles, registry = build_corpus()
    summary = None
    summary_path = REPORTS_DIR / "eval_summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    out = export_viewer_data(bundles, registry, VIEWER_DIR / "viewer_data.js", summary)
    print(f"-> {out}")
    print(f"打开 {VIEWER_DIR / 'index.html'} 查看（无需服务器）")


def cmd_all(args) -> None:
    cmd_build(args)
    cmd_eval(args)
    cmd_train(args)
    cmd_export_viewer(args)


def main(argv: list[str] | None = None) -> None:
    _stdout_utf8()
    parser = argparse.ArgumentParser(prog="label2brep", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="构建 silver 金标与查询样本")
    for name, help_text in (("train", "全量训练模型"), ("eval", "留一形状族交叉验证")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--with-aug", action="store_true", help="训练集加入扩增变体（artifacts/aug/）")
        p.add_argument("--aug", default=None, help="扩增数据文件路径（默认 artifacts/aug/aug_sections.jsonl）")
    p_map = sub.add_parser("map", help="单条查询映射")
    p_map.add_argument("section", help="截面 id，如 mu-shape-1")
    p_map.add_argument("query", help="Label 或工程师原话")
    sub.add_parser("export-viewer", help="导出前端 viewer 数据")
    p_aug = sub.add_parser("augment", help="数据扩增 T1–T5（加点拆线/拉伸/移壁/加删筋/刚体）")
    p_aug.add_argument("--per-section", type=int, default=20, help="每个截面的目标变体数")
    p_aug.add_argument("--seed", type=int, default=1)
    p_aug.add_argument("--quota", type=int, default=200, help="每个 label 的训练正例配额（0 关闭补齐）")
    p_aug.add_argument("--pilot", action="store_true",
                       help="只选 5 个形状族多样的截面，生成独立 pilot 产物（默认每截面 20 个）")
    p_aug.add_argument("--out", default=None, help=f"输出 jsonl（默认 {AUG_DIR / 'aug_sections.jsonl'}）")
    p_audit = sub.add_parser("audit-features", help="T1 拆线下的曲线特征敏感度审计")
    p_audit.add_argument("--seed", type=int, default=1)
    sub.add_parser("all", help="build + eval + train + export-viewer")
    args = parser.parse_args(argv)
    {
        "build": cmd_build, "train": cmd_train, "eval": cmd_eval,
        "map": cmd_map, "export-viewer": cmd_export_viewer, "all": cmd_all,
        "augment": cmd_augment, "audit-features": cmd_audit_features,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
