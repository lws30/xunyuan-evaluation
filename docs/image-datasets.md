# 数字和温度图片怎么用

先用 OCR 程序读图片，再把读出的文字和答案比较。OCR 就是图片文字识别。

## 1. 先看仓库里的样例

| 目录 | 里面有什么 |
|---|---|
| `datasets/readings_v3/` | 6 张数字牌、6 张温度屏和正确答案 |
| `datasets/temperature_v3/sample/` | 30 条温度样例，每条有完整面板和数字裁剪图，共 60 张图片 |
| `datasets/temperature_v3/` | 完整数据的标注、训练分组和预览图 |

这些图片由程序绘制。温度范围是 −20.0 至 120.0 ℃，有清晰、遮挡、模糊、遮挡加模糊、完全看不清五种情况。

## 2. 下载完整温度图片

完整数据有 15,000 条样本、30,000 张图片，解压后约 1.2 GB。在仓库根目录执行：

```bash
mkdir -p artifacts/datasets
curl -fL https://github.com/LWS30/xunyuan-evaluation/releases/download/v0.1.1/xunyuan-temperature-v3.zip \
  -o artifacts/datasets/xunyuan-temperature-v3.zip
curl -fL https://github.com/LWS30/xunyuan-evaluation/releases/download/v0.1.1/SHA256SUMS \
  -o artifacts/datasets/SHA256SUMS

# 检查下载文件是否完整
(cd artifacts/datasets && sha256sum -c SHA256SUMS)

# 解压到数据目录
python3 -m zipfile -e artifacts/datasets/xunyuan-temperature-v3.zip datasets/temperature_v3
```

解压后的 `train/`、`val/`、`test/` 都有 `panels/` 和 `crops/`。前者是完整面板，后者是数字区域的裁剪图。对应的 JSONL 标注一行写一条样本，图片路径以 `datasets/temperature_v3/` 为起点。

训练、验证、测试各有 12,000、1,500、1,500 条样本。同一个温度值的所有图片都放在同一组，使用时沿用这三组划分即可。

## 3. 标注里写了什么

| 字段 | 含义 |
|---|---|
| `id` / `split` | 样本编号，以及它属于训练、验证还是测试 |
| `image_path` / `crop_path` | 完整面板和数字裁剪图的位置 |
| `condition` | `normal` 清晰、`occlusion` 遮挡、`blur` 模糊、`mixed` 混合、`unreadable` 看不清 |
| `readable` | 图片上的字是否可读 |
| `status` | 可读时为 `ok`，看不清时为 `abstain` |
| `value` / `text` / `unit` | 数值文字、带单位的文字，以及单位 `C` |
| `display_roi_xyxy` | 数字区域在面板图中的位置 |
| `occluded_ink_fraction` / `gaussian_sigma` | 生成图片时使用的遮挡比例和模糊强度 |
| `source_value` / `source_group` | 生成时的原始温度和分组信息，用来检查数据划分 |

看不清的图片，`value` 和 `text` 是 `null`。识别时把图片交给 OCR 程序，再用答案检查结果。

## 4. 生成答案文件

先用仓库带的图片样例试一遍：

```bash
python3 -m xunyuan_eval reading-reference \
  --dataset datasets/temperature_v3/sample --split test \
  --output artifacts/temperature_sample_reference.json
```

下载完整图片后，把 `--dataset` 改成 `datasets/temperature_v3`，就会生成 1,500 条测试样本的答案。程序也会检查标注、图片文件和文件校验值。

## 5. 保存 OCR 识别结果

让自己的 OCR 程序读取图片，按下面的格式保存为 `my_predictions.json`，把 `value` 填成程序实际读出的文字：

```json
{
  "results": [
    {"id": "test_000000", "target_id": "test_000000", "status": "ok", "value": "58.1", "unit": "C"},
    {"id": "test_000007", "target_id": "test_000007", "status": "abstain", "reason": "display_occluded"}
  ]
}
```

温度样本的 `id` 和 `target_id` 都使用样本编号。数字牌样例则使用 `datasets/readings_v3/reference.json` 中对应的编号。

读出文字时写 `status: "ok"`。温度单位填 `C`，普通数字单位填 `null`。图片看不清时写 `status: "abstain"`，并在 `reason` 中写原因。

## 6. 比较结果

```bash
python3 -m xunyuan_eval readings \
  --predictions my_predictions.json \
  --reference artifacts/temperature_sample_reference.json \
  --output artifacts/temperature_reading_report.json
```

结果里会写对了几张、总共几张，以及每张的判断原因。少识别的图片也算在总数里。

普通数字逐字比较，保留前面的零、负号和小数点。温度默认允许 0.1 ℃ 误差，同时检查单位。看不清的图片，检查是否填写了原因。
