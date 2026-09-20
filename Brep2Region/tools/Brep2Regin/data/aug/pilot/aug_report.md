# 数据扩增报告（T1–T5）

- seed=1，每截面目标 20 个变体，label 配额 0
- 有标签截面 5 个；尝试 106 次，接受 100 个变体
- 每行保留 source_id/variant_id/shape_family/ops/seed/name_map/propagated_labels、source_manifest + source_sha256，以及六道校验门 validation_report。

## 按操作组合

| ops | 变体数 |
|---|---:|
| split | 22 |
| rigid+split | 12 |
| scale | 12 |
| rigid | 9 |
| scale+rigid+split | 9 |
| move+scale+split | 7 |
| move | 7 |
| scale+split | 5 |
| move+rigid+split | 4 |
| move+split | 3 |
| rib | 2 |
| rib+split | 2 |
| rib+scale+split | 2 |
| move+scale | 2 |
| rib+rigid | 1 |
| scale+rigid | 1 |

## 按形状族

| family | 源截面 | 变体 |
|---|---:|---:|
| B_shape | 1 | 20 |
| U_shape | 1 | 20 |
| ji_shape | 1 | 20 |
| m_shape | 1 | 20 |
| 目_shape | 1 | 20 |

## 按 label 的目标数（训练正例）

| label | 原始 | 变体 | 合计 | 配额达成 |
|---|---:|---:|---:|---|
| cavity | 4 | 80 | 84 | 是 |
| chamber | 5 | 105 | 110 | 是 |
| fillet | 10 | 200 | 210 | 是 |
| flange | 8 | 160 | 168 | 是 |
| internal_web | 2 | 48 | 50 | 是 |
| notch | 3 | 60 | 63 | 是 |
| web | 13 | 260 | 273 | 是 |

## 校验门拒绝统计

| 原因 | 次数 |
|---|---:|
| gate5_duplicate | 3 |
| gate1_cells | 2 |
| gate6_clearance | 1 |

拒绝明细（原因 | 操作组合 | 源截面，前 30）：

- gate5_duplicate | rigid | ji-shape-3: 3
- gate6_clearance | rib+split | mu-shape-1: 1
- gate1_cells | scale+rigid+split | ji-shape-3: 1
- gate1_cells | rib+scale+split | b-shape-1: 1

仿射交叉校验（校验门 4）：70 个变体，平均一致率 0.9992，最低 0.9778
几何最小间距（校验门 6）：中位数 3.74 mm，最小 0.88 mm
