"""Label2B-rep: Label -> DFC geometric entity grounding.

将标准 Label / 工程师原话映射到当前 DFC 截面中的具体几何实体
（Point / Curve / Face-cell），输出可高亮、可解释、可拒识的实体集合。

工程约束（路线二）：
- 不使用图片特征 / 图像识别网络；
- 不使用多模态大模型；
- 仅使用 DFC 原生 Point/Curve 几何 + 拓扑特征 + 轻量线性模型。
"""

__version__ = "0.1.0"
