# Brep2Regin

将 DFC 二维截面中的 Point/Curve 规范化为可审计的 Curve/Edge 记录，并为 Region
提供候选 Curve 映射。

## 使用

```powershell
python -m tools.Brep2Regin.extract_curve_edges sections/B-shape-2/B-shape-2.xml \
  -o artifacts/edge-demo/B-shape-2.json
```

也可以传入带同名 XML/Python 几何文件的 YAML。工具只读原始文件，输出 JSON、
`.edge_map.json` 和 `.manifest.json`，包含源文件 SHA256、解析器版本、端点有效性、
连通分量、分支/开环/闭环拓扑签名等信息。

`region_candidates` 只做 bbox 召回，明确标记为 `bbox_candidates_not_gold`；它不能
替代人工确认后的 Region→Curve 金标映射。缺失或歧义端点会进入 diagnostics，不能
静默生成可执行实体。

## 切割与数据扩增

`label2brep/augment.py` 在 Section 的二维 IR 副本上实现 T1–T5：

- **T1 split**：在线段上加点并拆成子线；通过 `name_map` 把父 Curve 的标签传播到全部子线，保持总长度；
- **T2 scale**：沿两个局部轴拉伸；
- **T3 move**：移动壁或筋；
- **T4 rib**：增加或删除筋，并重新计算闭合 cell；
- **T5 rigid**：旋转、镜像或变换坐标平面。

扩增不会读取图片或随机抖动坐标。每个变体都保存 `source_id`、`variant_id`、`ops`、
`seed`、`name_map`、`propagated_labels`、源文件 SHA256 和六道校验门报告。通过校验
的变体写入独立数据目录：

```powershell
python -m tools.Brep2Regin.label2brep augment --pilot --quota 0 \
  --out tools/Brep2Regin/data/aug/pilot/aug_sections.jsonl
python -m tools.Brep2Regin.label2brep augment --quota 200 \
  --out tools/Brep2Regin/data/aug/aug_sections.jsonl
```

本次提交包含 5 个代表截面 × 20 个 pilot 变体，以及 24 个有标签截面 × 20 个全量
变体。`data/manifest.json` 固定了源仓库 commit、54 个源文件哈希、生成参数和数据
哈希；可用下面的命令逐条重新生成并比对：

```powershell
python -m tools.Brep2Regin.verify_release --reproduce
```

当前标签是从已有 Region 标注传播的 silver label，仍需工程师确认后才能升级为 gold。

## 测试

在仓库根目录：

```powershell
pip install -r tools/Brep2Regin/requirements.txt
python -m pytest -q --disable-warnings tests/test_brep2regin.py tools/Brep2Regin/tests
python -m tools.Brep2Regin.verify_release
```

预期 49 个测试通过，发布校验报告 54 个源文件、100 条 pilot、480 条全量。完整步骤见仓库根目录 [README.md](../../README.md)。
