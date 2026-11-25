# 温度读屏数据集 V3

本数据集由本地合成显示图组成，温度范围为 −20.0 至 120.0 ℃，保留一位小数。每条样本提供完整面板和数字行裁剪两张 PNG，以及 JSONL 标注。

| 划分 | 样本数 | 图片数 |
|---|---:|---:|
| train | 12,000 | 24,000 |
| val | 1,500 | 3,000 |
| test | 1,500 | 3,000 |
| 合计 | 15,000 | 30,000 |

五种条件为正常、部分遮挡、模糊、遮挡叠加模糊、完全不可读。同一温度值及其所有增强只属于一个划分。不可读图片的 `value` 和 `text` 为 `null`，期望输出为拒识。

仓库包含完整的 `train.jsonl`、`val.jsonl`、`test.jsonl`、`manifest.json`、预览图，以及 `sample/` 下按划分和条件选取的 30 条样本、60 张图片。完整的 30,000 张图片请下载 [v0.1.1 Release](https://github.com/LWS30/xunyuan-evaluation/releases/tag/v0.1.1) 中的 `xunyuan-temperature-v3.zip`；下载、校验和诊断命令见[数据集说明](../../docs/datasets.md)。

![温度读屏样例](dataset_preview.png)

图像和标注采用仓库 MIT 许可。数据任务为 RGB 温度读屏；真实设备测温需要测温硬件及其标定。
