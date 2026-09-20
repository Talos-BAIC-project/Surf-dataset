"""排序模型：规则基线（B1）与纯 numpy 逻辑回归（B2）。

规则基线完全可解释，用于对照与冷启动兜底；
逻辑回归按 label 分别训练（数据量小、特征强，线性模型即够），
序列化为 JSON，推理为一次矩阵乘法（毫秒级）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .config import RANDOM_SEED
from .features import CURVE_FEATURE_NAMES, FACE_FEATURE_NAMES, SectionFeatures

F_C = {name: i for i, name in enumerate(CURVE_FEATURE_NAMES)}
F_F = {name: i for i, name in enumerate(FACE_FEATURE_NAMES)}


# ---------------------------------------------------------------------------
# 规则基线
# ---------------------------------------------------------------------------

def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def rule_curve_scores(label_short: str, X: np.ndarray) -> np.ndarray:
    """每条曲线的规则得分（0..1）。X: [n, len(CURVE_FEATURE_NAMES)]。"""
    if X.shape[0] == 0:
        return np.zeros(0)
    g = lambda name: X[:, F_C[name]]  # noqa: E731
    closed = g("section_closed")
    z = np.full(X.shape[0], -1.5)
    if label_short == "internal_web":
        z = -2.0 + 4.5 * g("separates_cells") + 0.8 * g("is_horizontal") * closed \
            - 1.0 * g("transition_like") - 0.8 * g("dangling")
    elif label_short == "web":
        z = -2.2 + 1.4 * g("on_outer") * closed + 1.2 * (1 - closed) \
            + 2.2 * g("run_len_rank") + 1.2 * g("aligned_long_axis") \
            - 2.5 * g("dangling") - 2.5 * g("transition_like") \
            - 1.2 * g("in_pocket") - 1.0 * g("run_has_tip_endpoint")
    elif label_short == "flange":
        z = -2.2 + 3.0 * g("dangling") + 2.2 * g("run_has_tip_endpoint") \
            - 1.5 * g("transition_like") + 0.6 * (1 - g("run_len_rank"))
    elif label_short == "outer_contour":
        z = -2.0 + 4.0 * g("on_outer") - 3.5 * g("dangling")
    elif label_short == "cavity":
        z = -1.6 + 2.0 * (1 - closed) + 1.8 * g("run_len_rank") - 2.0 * g("run_has_tip_endpoint") \
            - 1.5 * g("transition_like") - 1.0 * g("dangling")
    elif label_short == "notch":
        z = -2.2 + 3.6 * g("in_pocket") + 0.6 * g("transition_like") - 0.8 * g("dangling")
    elif label_short == "fillet":
        z = -2.5 + 5.0 * g("transition_like")
    return _sigmoid(z)


def rule_face_scores(X: np.ndarray) -> np.ndarray:
    """腔体（face）规则得分：大面优先；深腰 cell 让位给子腔。"""
    if X.shape[0] == 0:
        return np.zeros(0)
    g = lambda name: X[:, F_F[name]]  # noqa: E731
    is_sub = g("is_subcell")
    waist = g("waist_ratio")
    deep_waist = (waist < 0.6).astype(float)
    z = -1.0 + 2.5 * g("rel_area_to_max") \
        + 1.8 * is_sub * deep_waist - 2.2 * (1 - is_sub) * deep_waist
    return _sigmoid(z)


def rule_point_scores(feats: SectionFeatures) -> tuple[list[str], np.ndarray]:
    """点候选（倒角角点等）：转折明显的节点得分高。规则派生，v1 不训练。"""
    graph = feats.graph
    names, scores = [], []
    trans_curves = {c for c, t in graph.curve_topo.items() if t.transition_like}
    node_curves: dict[str, set[str]] = {}
    for e in graph.edges:
        for node in (e.node_a, e.node_b):
            if not node.startswith("J_"):
                node_curves.setdefault(node, set()).add(e.orig_curve)
    import math
    for pname, pt in graph.point_topo.items():
        rep = graph.point_rep.get(pname, pname)
        curves = {c for c in node_curves.get(rep, set()) if c in graph.geo.curves}
        if pt.degree < 2 or not curves:
            continue
        # 相邻曲线方向的最大夹角
        dirs = []
        for c in curves:
            poly = graph.geo.curves[c].polyline_local
            dx, dy = poly[-1][0] - poly[0][0], poly[-1][1] - poly[0][1]
            n = math.hypot(dx, dy)
            if n > 1e-9:
                dirs.append((dx / n, dy / n))
        best = 0.0
        for i in range(len(dirs)):
            for j in range(i + 1, len(dirs)):
                dot = abs(dirs[i][0] * dirs[j][0] + dirs[i][1] * dirs[j][1])
                best = max(best, math.degrees(math.acos(max(-1.0, min(1.0, dot)))))
        bonus = 0.3 if curves & trans_curves else 0.0
        names.append(pname)
        scores.append(min(1.0, best / 90.0 + bonus))
    return names, np.asarray(scores)


# ---------------------------------------------------------------------------
# 逻辑回归（纯 numpy，确定性）
# ---------------------------------------------------------------------------

@dataclass
class LogisticModel:
    feature_names: list[str]
    mean: np.ndarray | None = None
    std: np.ndarray | None = None
    weights: np.ndarray | None = None    # [d + 1]，末位为偏置
    n_pos: int = 0
    n_neg: int = 0

    def fit(self, X: np.ndarray, y: np.ndarray, l2: float = 0.5,
            epochs: int = 400, lr: float = 0.15, sample_weight: np.ndarray | None = None) -> None:
        """sample_weight：逐行权重（如"同一源截面的原始+变体共享权重 1"），与类权重相乘。"""
        rng = np.random.default_rng(RANDOM_SEED)
        _ = rng  # 保留种子接口；当前初始化为零向量，无随机性
        self.mean = X.mean(axis=0)
        self.std = X.std(axis=0)
        self.std[self.std < 1e-9] = 1.0
        Xn = (X - self.mean) / self.std
        Xb = np.hstack([Xn, np.ones((Xn.shape[0], 1))])
        self.n_pos = int(y.sum())
        self.n_neg = int(len(y) - self.n_pos)
        w_row = np.ones(len(y)) if sample_weight is None else np.asarray(sample_weight, dtype=float)
        # 有效样本量 = 行权重之和（无扩增时等于行数）。数据项与 L2 项都按它归一，
        # 这样把一个截面复制成 20 个高度相关的变体不会让正则化相对变弱 20 倍。
        n_eff = max(float(w_row.sum()), 1e-9)
        pos_mass = float(w_row[y > 0.5].sum())
        neg_mass = float(w_row[y <= 0.5].sum())
        pos_w = min(max(neg_mass / max(pos_mass, 1e-9), 1.0), 12.0)
        sw = np.where(y > 0.5, pos_w, 1.0) * w_row
        sw = sw * (n_eff / sw.sum())

        w = np.zeros(Xb.shape[1])
        m = np.zeros_like(w)
        v = np.zeros_like(w)
        b1, b2, eps = 0.9, 0.999, 1e-8
        for t in range(1, epochs + 1):
            p = _sigmoid(Xb @ w)
            grad = Xb.T @ (sw * (p - y)) / n_eff
            grad[:-1] += l2 * w[:-1] / n_eff
            m = b1 * m + (1 - b1) * grad
            v = b2 * v + (1 - b2) * grad * grad
            mh = m / (1 - b1**t)
            vh = v / (1 - b2**t)
            w -= lr * mh / (np.sqrt(vh) + eps)
        self.weights = w

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if X.shape[0] == 0 or self.weights is None:
            return np.zeros(X.shape[0])
        Xn = (X - self.mean) / self.std
        Xb = np.hstack([Xn, np.ones((Xn.shape[0], 1))])
        return _sigmoid(Xb @ self.weights)

    def top_contributions(self, x: np.ndarray, k: int = 3) -> list[str]:
        """单样本的前 k 个正贡献特征（可解释证据）。"""
        if self.weights is None:
            return []
        xn = (x - self.mean) / self.std
        contrib = xn * self.weights[:-1]
        idx = np.argsort(-contrib)[:k]
        return [self.feature_names[i] for i in idx if contrib[i] > 0.05]

    def to_dict(self) -> dict:
        return {
            "feature_names": self.feature_names,
            "mean": self.mean.tolist(), "std": self.std.tolist(),
            "weights": self.weights.tolist(),
            "n_pos": self.n_pos, "n_neg": self.n_neg,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LogisticModel":
        m = cls(feature_names=list(d["feature_names"]))
        m.mean = np.asarray(d["mean"])
        m.std = np.asarray(d["std"])
        m.weights = np.asarray(d["weights"])
        m.n_pos = d.get("n_pos", 0)
        m.n_neg = d.get("n_neg", 0)
        return m


# ---------------------------------------------------------------------------
# 按 label 组织的模型库
# ---------------------------------------------------------------------------

MIN_POS_SECTIONS = 2      # 少于该正例截面数则不训练，回退规则

@dataclass
class ModelBank:
    curve_models: dict[str, LogisticModel] = field(default_factory=dict)   # label_short -> model
    face_model: LogisticModel | None = None
    trained_on: list[str] = field(default_factory=list)

    def train(self, bundles: list, samples: list, section_weights: dict[str, float] | None = None) -> None:
        """bundles: list[SectionBundle]（含 features）；samples: 训练截面的 generic 样本。

        section_weights: 截面 -> 行权重。扩增时用它让"同一源截面的原始 + 全部变体"合计权重
        仍为 1，扩增只增加几何多样性，不放大某个截面（及其负例）的话语权。
        """
        feats_by_section = {b.record.section_id: b.features for b in bundles}
        self.trained_on = sorted(feats_by_section)
        section_weights = section_weights or {}

        def w_of(section_id: str) -> float:
            return float(section_weights.get(section_id, 1.0))

        by_label: dict[str, list] = {}
        face_rows: list[tuple[str, list[str]]] = []
        for s in samples:
            if s.kind != "generic" or s.section_id not in feats_by_section:
                continue
            short = s.label_id.rsplit(".", 1)[-1]
            if s.entity_type == "face":
                face_rows.append((s.section_id, s.target_faces))
            elif s.entity_type == "curve":
                by_label.setdefault(short, []).append((s.section_id, set(s.target_curves)))

        for short, rows in by_label.items():
            if len(rows) < MIN_POS_SECTIONS:
                continue
            X_list, y_list, w_list = [], [], []
            for section_id, positive in rows:
                f = feats_by_section[section_id]
                X_list.append(f.curve_matrix)
                y_list.append(np.array([1.0 if c in positive else 0.0 for c in f.curve_names]))
                w_list.append(np.full(len(f.curve_names), w_of(section_id)))
            X = np.vstack(X_list)
            y = np.concatenate(y_list)
            if y.sum() < 2:
                continue
            model = LogisticModel(feature_names=list(CURVE_FEATURE_NAMES))
            model.fit(X, y, sample_weight=np.concatenate(w_list))
            self.curve_models[short] = model

        if len(face_rows) >= MIN_POS_SECTIONS:
            X_list, y_list, w_list = [], [], []
            for section_id, positive in face_rows:
                f = feats_by_section[section_id]
                if f.face_matrix.shape[0] == 0:
                    continue
                X_list.append(f.face_matrix)
                pos = set(positive)
                y_list.append(np.array([1.0 if fid in pos else 0.0 for fid in f.face_ids]))
                w_list.append(np.full(len(f.face_ids), w_of(section_id)))
            if X_list:
                X = np.vstack(X_list)
                y = np.concatenate(y_list)
                if y.sum() >= 2:
                    self.face_model = LogisticModel(feature_names=list(FACE_FEATURE_NAMES))
                    self.face_model.fit(X, y, sample_weight=np.concatenate(w_list))

    # -- 打分（自动回退规则） ------------------------------------------------
    def score_curves(self, label_short: str, feats: SectionFeatures) -> tuple[np.ndarray, str]:
        model = self.curve_models.get(label_short)
        if model is not None:
            return model.predict_proba(feats.curve_matrix), "logreg"
        return rule_curve_scores(label_short, feats.curve_matrix), "rules_fallback"

    def score_faces(self, feats: SectionFeatures) -> tuple[np.ndarray, str]:
        if self.face_model is not None:
            return self.face_model.predict_proba(feats.face_matrix), "logreg"
        return rule_face_scores(feats.face_matrix), "rules_fallback"

    # -- 序列化 --------------------------------------------------------------
    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "trained_on": self.trained_on,
            "curve_models": {k: m.to_dict() for k, m in self.curve_models.items()},
            "face_model": self.face_model.to_dict() if self.face_model else None,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "ModelBank":
        d = json.loads(path.read_text(encoding="utf-8"))
        bank = cls()
        bank.trained_on = d.get("trained_on", [])
        bank.curve_models = {k: LogisticModel.from_dict(v) for k, v in d.get("curve_models", {}).items()}
        if d.get("face_model"):
            bank.face_model = LogisticModel.from_dict(d["face_model"])
        return bank


class RulesBank(ModelBank):
    """纯规则打分（B1 基线）：与 ModelBank 同接口，永远走规则。"""

    def score_curves(self, label_short: str, feats: SectionFeatures) -> tuple[np.ndarray, str]:
        return rule_curve_scores(label_short, feats.curve_matrix), "rules"

    def score_faces(self, feats: SectionFeatures) -> tuple[np.ndarray, str]:
        return rule_face_scores(feats.face_matrix), "rules"


class HybridBank(ModelBank):
    """混合打分（B2+B1）：规则与逻辑回归的均值。

    小数据量下逻辑回归跨形状族迁移不稳，规则提供保底；
    数据增长后可平滑退回纯模型。
    """

    def score_curves(self, label_short: str, feats: SectionFeatures) -> tuple[np.ndarray, str]:
        rule = rule_curve_scores(label_short, feats.curve_matrix)
        model = self.curve_models.get(label_short)
        if model is None:
            return rule, "rules_fallback"
        return 0.5 * rule + 0.5 * model.predict_proba(feats.curve_matrix), "hybrid"

    def score_faces(self, feats: SectionFeatures) -> tuple[np.ndarray, str]:
        rule = rule_face_scores(feats.face_matrix)
        if self.face_model is None:
            return rule, "rules_fallback"
        return 0.5 * rule + 0.5 * self.face_model.predict_proba(feats.face_matrix), "hybrid"
