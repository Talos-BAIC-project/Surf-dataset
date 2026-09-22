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

## Label → Region 预览

`label_region_viewer/index.html` 是 pub2 上那一版可查看的测试预览：10 个样本、20 条已导出 case，可看结构和规则输出。它还不能实时输入新提示词，边名在密集处会重叠，missing/extra 也不能当成正式准确率。详细边界见 [`label_region_viewer/README.md`](label_region_viewer/README.md)。
