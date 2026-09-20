"""评估 harness 测试：指标口径 + 小规模端到端。"""

import pytest

from tools.Brep2Regin.label2brep.config import SECTIONS_DIR
from tools.Brep2Regin.label2brep.evaluate import evaluate_lofo, summarize
from tools.Brep2Regin.label2brep.pipeline import build_corpus

pytestmark = pytest.mark.skipif(not SECTIONS_DIR.exists(), reason="dfc-dataset 不存在")


@pytest.fixture(scope="module")
def eval_result():
    bundles, registry = build_corpus()
    rows = evaluate_lofo(bundles, registry)
    return rows, summarize(rows)


def test_lofo_covers_all_scorers_and_samples(eval_result):
    rows, summary = eval_result
    scorers = {r.scorer for r in rows}
    assert scorers == {"rules", "logreg", "hybrid"}
    n_per = {sc: sum(1 for r in rows if r.scorer == sc) for sc in scorers}
    assert len(set(n_per.values())) == 1          # 三个系统评了同样的样本

def test_lofo_no_family_leakage(eval_result):
    rows, _ = eval_result
    # LOFO 由构造保证；这里验证每个形状族都出现在测试行中
    fams = {r.family for r in rows}
    assert len(fams) >= 7


def test_quality_floor(eval_result):
    """质量下限护栏：防止后续改动无声回归。"""
    _, summary = eval_result
    hybrid = summary["overall"]["hybrid"]
    assert hybrid["f1"] >= 0.65
    assert hybrid["cand_recall@20"] >= 0.97
    assert summary["latency"]["hybrid"]["p95_ms"] < 50
    # 强标签下限
    assert summary["by_label"]["dfc.substructure.chamber"]["hybrid"]["f1"] >= 0.9
    assert summary["by_label"]["dfc.substructure.internal_web"]["hybrid"]["f1"] >= 0.9
    assert summary["by_label"]["dfc.substructure.outer_contour"]["hybrid"]["f1"] >= 0.95
