# Brep2Region

从 DFC 二维截面提取可审计的 Curve/Edge，并为 Region 提供候选 Curve 映射。

本目录是 Surf-dataset 里的 Brep2Region 子集，内容来自 `Talos-BAIC-project/dfc-dataset` PR #12（`181fffe`）。

## 内容

- `sections/`：27 个源截面（对应 dfc-dataset `e45fe32`）
- `tools/Brep2Regin/`：曲线提取、T1–T5 扩增、发布校验
- `tests/test_brep2regin.py`：提取器回归测试

标签质量为 `propagated_silver_not_engineer_gold`，需工程师确认后才能升级为 gold。

## 如何测试

在 **`Brep2Region/`** 目录下执行，不要在仓库根目录跑。Python 3.12+ 即可。

```powershell
cd Brep2Region
pip install -r tools/Brep2Regin/requirements.txt
```

### 1. 单元测试

```powershell
python -m pytest -q --disable-warnings tests/test_brep2regin.py tools/Brep2Regin/tests
```

预期：`49 passed`。覆盖提取器（开环/闭环/分支、只读源文件、bbox 候选）以及 T1–T5 扩增、几何、图、标签、映射、评估。

如果只跑提取器：

```powershell
python -m pytest -q --disable-warnings tests/test_brep2regin.py
```

### 2. 发布校验

核对 `data/manifest.json` 里 54 个源文件哈希，以及 100 条 pilot + 480 条全量扩增记录：

```powershell
python -m tools.Brep2Regin.verify_release
```

预期输出包含 `source_files_verified: 54`、`pilot: 100`、`full: 480`。

可选：按固定 seed 重新生成两批扩增并逐条比对（更慢）：

```powershell
python -m tools.Brep2Regin.verify_release --reproduce
```

### 3. 手工抽一条提取

```powershell
python -m tools.Brep2Regin.extract_curve_edges sections/B-shape-2/B-shape-2.xml `
  -o artifacts/edge-demo/B-shape-2.json
```

源 XML/YAML 不会被改写。输出里的 `region_candidates` 只是 bbox 召回（`bbox_candidates_not_gold`），不能当金标。

工具细节见 [tools/Brep2Regin/README.md](tools/Brep2Regin/README.md)。
