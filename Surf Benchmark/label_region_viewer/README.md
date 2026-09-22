# Label → Region 结构预览（非最终验收）

这是 pub2 上已核对过的可查看预览，不是完整测试工具。文件来自
`/home/dataset-local/batchcom/DP/tests/label_region/aug_sample/viewer`：
10 个 T1–T5 样本、20 个已导出 case。打开 `index.html`，或在本目录执行：

```powershell
python -m http.server 7897
```

页面可以看截面结构、边的稳定名称，并切换参考 Region 与规则输出。也能看到
`resolved`、`needs_confirmation`、`not_found`，以及对应的实体引用和证据。

本机 `http://127.0.0.1:7898/index.html` 只是本机预览。pub2 上的服务只监听远端本机地址，从这台电脑访问需要 SSH 端口转发。

## 还没完成

| 项目 | 当前状态 |
|---|---|
| 任意输入新的 Prompt，实时返回 Region | 只能切换已导出的 20 个 case，没有连接实时 API |
| 边名清晰排布 | 名称已经显示，密集区域会重叠 |
| “左侧的梁”等 selector 对比 | 参考层按 Label 展示全部相关区域，还不是逐 case 的精确目标。页面上的 missing/extra 不能当作正式准确率 |
| dfc-data JSON 导出 | `dfc_snapshots/` 可被 JSON v3 读取，但曲线目前标成直线，控制点还没保留，不是无损转换 |
| T1 拆线后的识别 | 页面能看出失败，规则本身还没修。可视化完成不等于识别通过 |

当前不应标记为最终验收通过。
