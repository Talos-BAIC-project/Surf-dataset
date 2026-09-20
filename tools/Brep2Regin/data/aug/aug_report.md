# 数据扩增报告（T1–T5）

- seed=1，每截面目标 20 个变体，label 配额 200
- 有标签截面 24 个；尝试 532 次，接受 480 个变体
- 每行保留 source_id/variant_id/shape_family/ops/seed/name_map/propagated_labels、source_manifest + source_sha256，以及六道校验门 validation_report。

## 按操作组合

| ops | 变体数 |
|---|---:|
| split | 119 |
| scale | 69 |
| move | 41 |
| scale+rigid+split | 38 |
| rigid | 36 |
| move+scale+split | 29 |
| scale+split | 25 |
| rigid+split | 22 |
| scale+rigid | 17 |
| move+rigid+split | 17 |
| move+split | 14 |
| rib | 12 |
| move+scale | 8 |
| rib+scale+split | 7 |
| rib+split | 5 |
| rib+rigid+split | 4 |
| move+rigid | 4 |
| move+scale+rigid | 3 |
| rib+rigid | 2 |
| rib+scale | 2 |
| rib+scale+rigid | 2 |
| rib+move+split | 2 |
| rib+move+rigid | 1 |
| rib+move | 1 |

## 按形状族

| family | 源截面 | 变体 |
|---|---:|---:|
| B_shape | 4 | 80 |
| U_shape | 1 | 20 |
| ji_shape | 3 | 60 |
| kou_shape | 4 | 80 |
| m_shape | 3 | 60 |
| ri_shape | 5 | 100 |
| 目_shape | 4 | 80 |

## 按 label 的目标数（训练正例）

| label | 原始 | 变体 | 合计 | 配额达成 |
|---|---:|---:|---:|---|
| cavity | 10 | 200 | 210 | 是 |
| chamber | 34 | 706 | 740 | 是 |
| fillet | 10 | 200 | 210 | 是 |
| flange | 25 | 500 | 525 | 是 |
| internal_web | 13 | 301 | 314 | 是 |
| notch | 13 | 260 | 273 | 是 |
| web | 26 | 520 | 546 | 是 |

## 校验门拒绝统计

| 原因 | 次数 |
|---|---:|
| gate5_duplicate | 19 |
| gate1_cells | 15 |
| gate4_affine | 12 |
| gate6_clearance | 3 |
| not_applicable:move | 2 |
| gate6_bbox_ratio | 1 |

拒绝明细（原因 | 操作组合 | 源截面，前 30）：

- gate4_affine | rigid | mu-shape-5: 5
- gate5_duplicate | rigid | ji-shape-3: 3
- gate5_duplicate | rigid | kou-shape-3: 3
- gate5_duplicate | rigid | mu-shape-2: 3
- gate1_cells | scale | ri-shape-3: 3
- gate5_duplicate | rigid | kou-shape-1: 2
- gate4_affine | scale | kou-shape-4: 2
- gate5_duplicate | rigid | ri-shape-1: 2
- gate1_cells | split | ri-shape-3: 2
- gate1_cells | scale+split | ri-shape-3: 2
- gate1_cells | move+scale+split | ri-shape-3: 2
- gate1_cells | rib+scale+split | b-shape-1: 1
- not_applicable:move | move+scale+split | B-shape-3: 1
- not_applicable:move | move+rigid+split | B-shape-3: 1
- gate1_cells | move+split | B-shape-3: 1
- gate5_duplicate | rigid | B-shape-6: 1
- gate5_duplicate | rigid | ji-shape-2: 1
- gate1_cells | scale+rigid+split | ji-shape-3: 1
- gate5_duplicate | move | kou-shape-1: 1
- gate6_clearance | rib+scale+split | kou-shape-4: 1
- gate4_affine | scale+split | kou-shape-4: 1
- gate4_affine | scale+rigid+split | kou-shape-4: 1
- gate5_duplicate | rigid | m-shape-2: 1
- gate6_clearance | rib+split | mu-shape-1: 1
- gate4_affine | rigid | mu-shape-4: 1
- gate4_affine | rigid+split | mu-shape-5: 1
- gate6_bbox_ratio | move+scale+rigid | ri-shape-1: 1
- gate6_clearance | rib+split | ri-shape-1: 1
- gate1_cells | scale+rigid+split | ri-shape-3: 1
- gate1_cells | rib+scale+split | ri-shape-3: 1

仿射交叉校验（校验门 4）：326 个变体，平均一致率 0.9990，最低 0.9500
几何最小间距（校验门 6）：中位数 4.33 mm，最小 0.88 mm
