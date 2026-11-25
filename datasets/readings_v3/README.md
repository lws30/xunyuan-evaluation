# 数字牌和温度屏图片

这里有 12 张 V3 场景图片：6 张数字牌、6 张温度屏，都是程序绘制的面板图。

图片放在 `images/`，正确答案放在 `reference.json`。数字包括 `00127`、`-08.3`、`083`、`0042`、`19.07`、`-12`；温度单位是 `C`。

先用自己的 OCR 程序识别图片，把结果保存成 `my_predictions.json`，再运行：

```bash
python3 -m xunyuan_eval readings \
  --predictions my_predictions.json \
  --reference datasets/readings_v3/reference.json \
  --output artifacts/panel_reading_report.json
```

打开结果文件，查看识别对了几张、错在哪里。预测文件的写法见[图片使用说明](../../docs/datasets.md)。

这组图片适合先跑通识别和评分步骤。需要训练数据时，可以使用[温度图片数据集](../temperature_v3/)。
