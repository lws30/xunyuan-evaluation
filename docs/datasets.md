# 右侧视频怎么用

共十段视频，每段 10 分钟，分辨率 640×360，每秒 5 帧。标牌贴在走廊右墙上，相机沿走廊移动采集画面。

- **8 段训练视频**：每段配正确答案、出现时间和标牌位置。可以反复训练、查看错误、修改模型。
- **2 段测试视频**：用于最后评分，答案由组织方保存。

每段含 6 个数字牌和 6 个温度屏。标牌的位置、大小和相机角度随视频变化，包含清晰、模糊、运动模糊、部分遮挡和完全看不清五种情况。

## 1. 下载

在[v0.2.0 下载页](https://github.com/LWS30/xunyuan-evaluation/releases/tag/v0.2.0)下载训练包、测试包和校验文件：

```bash
mkdir -p artifacts/downloads
curl -fL https://github.com/LWS30/xunyuan-evaluation/releases/download/v0.2.0/xunyuan-v2-training-videos.zip \
  -o artifacts/downloads/xunyuan-v2-training-videos.zip
curl -fL https://github.com/LWS30/xunyuan-evaluation/releases/download/v0.2.0/xunyuan-v2-test-videos.zip \
  -o artifacts/downloads/xunyuan-v2-test-videos.zip
curl -fL https://github.com/LWS30/xunyuan-evaluation/releases/download/v0.2.0/SHA256SUMS \
  -o artifacts/downloads/SHA256SUMS
(cd artifacts/downloads && sha256sum -c SHA256SUMS)
python -m zipfile -e artifacts/downloads/xunyuan-v2-training-videos.zip datasets/video_v2
python -m zipfile -e artifacts/downloads/xunyuan-v2-test-videos.zip datasets/video_v2
```

解压后：

```text
video_v2/
  manifest.json
  train/
    train01.mp4 ... train08.mp4
    reference.json
  test/
    test01.mp4
    test02.mp4
```

## 2. 训练后检查一段视频

```bash
python -m xunyuan_eval read-videos \
  --model my_team/reader.onnx --videos datasets/video_v2 \
  --split train --video train01 --output artifacts/train01_predictions.json
python -m xunyuan_eval score-video \
  --predictions artifacts/train01_predictions.json \
  --reference datasets/video_v2/train/reference.json --video train01 \
  --output artifacts/train01_score.json
```

打开 `train01_score.json`，查看正确答案、模型读出的文字，以及对了几张、哪些标牌出错。修改模型后，再运行这两步。去掉 `--video train01`，可以读取和检查全部训练视频。

## 3. 答案里有什么

每个标牌记录视频编号、出现的起止时间、每帧位置、数字或温度，以及是否看得清。看不清的标牌，答案中的读数为 `null`，识别结果填写看不清的原因。

评分时按画面时间和标牌位置找到对应答案，再比较读数。每个标牌只计一次，使用可信度最高的一次输出。

## 4. 自己贴标牌、生成视频

把 12 个数值写进 `content.json`，格式见[内容样例](../datasets/video_v2/content.example.json)，再生成：

```bash
MUJOCO_GL=egl python -m tools.build_video_v2 \
  --output artifacts/my_videos --private organizer/my_video_answers \
  --content content.json
```

自定义内容用于训练视频，测试视频另外随机生成。选择新的输出目录即可保留每次生成的数据。

原有的数字和温度静态图片仍可用于训练，见[图片数据说明](image-datasets.md)。
