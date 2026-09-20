"""集中路径与常量配置。"""

from __future__ import annotations

import os
from pathlib import Path

# 工具根（tools/Brep2Regin/）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 默认读取本仓库 sections/；允许使用独立的数据快照。
_DEFAULT_DATASET = PROJECT_ROOT.parents[1]
DATASET_ROOT = Path(os.environ.get("DFC_DATASET_ROOT", str(_DEFAULT_DATASET)))
SECTIONS_DIR = DATASET_ROOT / "sections"

# 生成产物
ARTIFACTS_DIR = Path(os.environ.get("DFC_ARTIFACTS_DIR", str(PROJECT_ROOT / "artifacts")))
REPORTS_DIR = ARTIFACTS_DIR / "reports"
VIEWER_DIR = PROJECT_ROOT / "viewer"

# 几何容差（单位 mm；截面尺度 ~30-260mm）
GEOM_EPS = 1e-6
# bbox 命中判定时的外扩容差
BBOX_TOL_ABS = 1.2
BBOX_TOL_REL = 0.02  # 相对截面对角线

# 曲线视为"过渡段（倒角/圆角）"的长度上限（相对截面对角线）
TRANSITION_MAX_REL_LEN = 0.10

# 决策阈值
CONF_RESOLVED = 0.75
CONF_NEEDS_CONFIRMATION = 0.40

RANDOM_SEED = 20260827
