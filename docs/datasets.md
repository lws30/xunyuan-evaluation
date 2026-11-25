# 数字与温度图片的获取和使用

## 随仓库提供的图片

- `datasets/readings_v3/`：V3 场景的 6 张数字牌、6 张温度屏及参考答案。
- `datasets/temperature_v3/sample/`：训练、验证、测试各 10 条温度样本。每个划分从正常、遮挡、模糊、混合、不可读五种情况各选两条，共 30 条样本、60 张图片。
- `datasets/temperature_v3/`：完整数据的 15,000 条标注、原始划分清单和预览图。

这些图片来源于本机生成的开发资源，图像和标注采用仓库 MIT 许可。温度图是合成的 RGB 显示图，读数范围为 −20.0 至 120.0 ℃。

## 获取完整温度图片

在仓库根目录执行以下命令。完整压缩包内含 30,000 张图片、15,000 条标注、清单、说明与许可；解压后占用约 1.2 GB。

```bash
mkdir -p artifacts/datasets
curl -fL https://github.com/LWS30/xunyuan-evaluation/releases/download/v0.1.1/xunyuan-temperature-v3.zip \
  -o artifacts/datasets/xunyuan-temperature-v3.zip
curl -fL https://github.com/LWS30/xunyuan-evaluation/releases/download/v0.1.1/SHA256SUMS \
  -o artifacts/datasets/SHA256SUMS
(cd artifacts/datasets && sha256sum -c SHA256SUMS)
python3 -m zipfile -e artifacts/datasets/xunyuan-temperature-v3.zip datasets/temperature_v3
```

下载大小与 SHA-256 同时记录在 `datasets/temperature_v3/download.json`。解压后，`train/`、`val/`、`test/` 中各有 `panels/` 与 `crops/`；同名 JSONL 中的路径相对于 `datasets/temperature_v3/`。

| 字段 | 含义 |
|---|---|
| `id` / `split` | 样本标识与训练、验证或测试划分 |
| `image_path` / `crop_path` | 完整面板与数字行裁剪的相对路径 |
| `condition` | `normal`、`occlusion`、`blur`、`mixed`、`unreadable` |
| `readable` / `status` | 是否可读；不可读样本的期望行为为 `abstain` |
| `value` / `text` / `unit` | 可读时的数值字符串、带单位文本和单位 `C` |
| `display_roi_xyxy` | 数字行在完整面板中的矩形区域 |
| `occluded_ink_fraction` / `gaussian_sigma` | 合成遮挡比例与模糊参数 |
| `source_value` / `source_group` | 生成与分组信息；仅用于数据审计，识别程序只读取图片 |

训练、验证、测试分别有 12,000、1,500、1,500 条样本。同一温度值及其所有增强均归入同一划分；使用数据时应保留原有划分。不可读图片的 `value`、`text` 为空，不要求猜测被完全遮住的字符。

## 从图片运行读数诊断

先导出图片对应的参考文件。无需下载完整数据即可验证仓库内的图片样例：

```bash
python3 -m xunyuan_eval reading-reference \
  --dataset datasets/temperature_v3/sample --split test \
  --output artifacts/temperature_sample_reference.json
```

完整数据下载并解压后，将 `--dataset` 改为 `datasets/temperature_v3` 即可生成全部测试样本的参考文件。导出时会校验标注划分、样本 ID、可读性和图片是否存在；完整标注还会核对原始清单中的 SHA-256。

将选定划分的图片送入自己的 OCR 模型，保存以下格式的预测。`id` 与 `target_id` 必须对应参考事件；温度数据的两者均为原样本 ID。可读预测的 `value` 必须是字符串；温度单位为 `C`，普通数字单位为 `null`。拒识时应提供非空原因。

```json
{
  "results": [
    {"id": "test_000000", "target_id": "test_000000", "status": "ok", "value": "31.4", "unit": "C"},
    {"id": "test_000001", "target_id": "test_000001", "status": "abstain", "reason": "display_occluded"}
  ]
}
```

上面仅展示格式，ID 和数值请使用实际识别结果。然后运行：

```bash
python3 -m xunyuan_eval readings \
  --predictions my_predictions.json \
  --reference artifacts/temperature_sample_reference.json \
  --output artifacts/temperature_reading_report.json
```

结果包括正确数、固定分母和逐项原因。普通数字严格比较字符串；温度默认允许 0.1 ℃ 误差并检查单位；不可读图片检查是否明确拒识。读数诊断单独报告，`competition_score` 为 `null`。
