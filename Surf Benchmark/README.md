# Surf Benchmark

Text2CAD 评测集，从本地 `Text2CAD Bench` 导入。

## 布局

```
Surf Benchmark/
└── Text2CAD_Bench/
    └── bench_release_20260806/
        ├── prompts.csv
        └── step/
            ├── L1/   # 200 STEP
            ├── L2/   # 200 STEP
            └── L3/   # 100 STEP
```

未提交源目录里的 `Text2CAD_Bench.zip`（与解压内容重复）。

## Label → Region viewer

`label_region_viewer/index.html` 是一套无需后端即可打开的结构可视化测试
查看器。它覆盖 10 个样本、20 条单操作用例，给截面的每条边显示稳定几何
名称，并同时叠加 silver Region 标注与规则解析结果，便于直接观察 Region
输出和实体引用的差异。详细使用说明见
[`label_region_viewer/README.md`](label_region_viewer/README.md)。
