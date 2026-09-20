# Surf-dataset (Brep2Region)

从 DFC 二维截面提取可审计的 Curve/Edge，并为 Region 提供候选 Curve 映射。

本仓库内容来自 `Talos-BAIC-project/dfc-dataset` PR #12（`181fffe`），在独立仓库中发布。

## 内容

- `sections/`：27 个源截面（对应 dfc-dataset `e45fe32`）
- `tools/Brep2Regin/`：曲线提取、T1–T5 扩增、发布校验
- `tests/test_brep2regin.py`：提取器回归测试

标签质量为 `propagated_silver_not_engineer_gold`，需工程师确认后才能升级为 gold。

## 使用

```powershell
pip install -r tools/Brep2Regin/requirements.txt
python -m tools.Brep2Regin.extract_curve_edges sections/B-shape-2/B-shape-2.xml -o artifacts/edge-demo/B-shape-2.json
python -m pytest -q tests/test_brep2regin.py tools/Brep2Regin/tests
python -m tools.Brep2Regin.verify_release
```
