# Surf-dataset

汽车白车身相关的曲面 / 截面数据与评测集。

| 目录 | 内容 |
|---|---|
| [Brep2Region/](Brep2Region/) | B-rep / 截面 → Region：曲线提取、T1–T5 扩增、单测 |
| [Surf Benchmark/](Surf%20Benchmark/) | Text2CAD Bench：自然语言提示 + STEP 金标 |

## Brep2Region

测试请进入子目录后再跑：

```powershell
cd Brep2Region
pip install -r tools/Brep2Regin/requirements.txt
python -m pytest -q --disable-warnings tests/test_brep2regin.py tools/Brep2Regin/tests
python -m tools.Brep2Regin.verify_release
```

预期 49 个测试通过。详见 [Brep2Region/README.md](Brep2Region/README.md)。

## Surf Benchmark

来源：本地 `Text2CAD Bench`（`bench_release_20260806`）。

- `Text2CAD_Bench/bench_release_20260806/prompts.csv`：评测提示
- `Text2CAD_Bench/bench_release_20260806/step/L1`：200 个 STEP
- `Text2CAD_Bench/bench_release_20260806/step/L2`：200 个 STEP
- `Text2CAD_Bench/bench_release_20260806/step/L3`：100 个 STEP

未纳入重复的 `Text2CAD_Bench.zip`。
