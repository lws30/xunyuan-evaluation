# 数字牌与温度屏图片

这里收录本机 V3 开发场景生成的 12 张面板纹理图片：6 张普通数字牌、6 张温度屏。它们作为公开开发样例，均有可见读数。

`reference.json` 中每个事件包含 `id`、`target_id`、`kind`、`readable`、`answer`、`unit` 和 `image_path`；图片路径相对于本目录。

普通数字按字符串保存，包括 `00127`、`-08.3`、`083`、`0042`、`19.07`、`-12`；温度屏的单位为 `C`。使用自己的 OCR 识别图片后，可将预测文件交给现有诊断命令：

```bash
python3 -m xunyuan_eval readings \
  --predictions my_predictions.json \
  --reference datasets/readings_v3/reference.json \
  --output artifacts/panel_reading_report.json
```

预测格式见[数据集说明](../../docs/datasets.md)。本组为固定开发面板，未划分训练集和测试集；需要按温度值分组的训练数据时，使用温度读屏 V3 数据集。

图像和标注采用仓库 MIT 许可。
