"""模型层测试：逻辑回归可学习、确定性、序列化往返。"""

import numpy as np

from tools.Brep2Regin.label2brep.features import CURVE_FEATURE_NAMES
from tools.Brep2Regin.label2brep.models import LogisticModel


def _toy():
    rng = np.random.default_rng(7)
    X = rng.normal(size=(200, 4))
    y = (X[:, 0] + 0.5 * X[:, 2] > 0).astype(float)
    return X, y


def test_logreg_learns_separable():
    X, y = _toy()
    m = LogisticModel(feature_names=["a", "b", "c", "d"])
    m.fit(X, y)
    pred = (m.predict_proba(X) > 0.5).astype(float)
    assert (pred == y).mean() > 0.95


def test_logreg_deterministic():
    X, y = _toy()
    m1 = LogisticModel(feature_names=["a", "b", "c", "d"])
    m2 = LogisticModel(feature_names=["a", "b", "c", "d"])
    m1.fit(X, y)
    m2.fit(X, y)
    assert np.allclose(m1.weights, m2.weights)


def test_serialization_roundtrip():
    X, y = _toy()
    m = LogisticModel(feature_names=["a", "b", "c", "d"])
    m.fit(X, y)
    m2 = LogisticModel.from_dict(m.to_dict())
    assert np.allclose(m.predict_proba(X), m2.predict_proba(X))


def test_feature_names_consistent():
    assert len(set(CURVE_FEATURE_NAMES)) == len(CURVE_FEATURE_NAMES)
