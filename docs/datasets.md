# 右侧数字和温度视频

十段视频，每段十分钟，640×360，每秒五帧。标牌贴在走廊右墙，相机沿走廊移动。

八段训练视频带答案，可反复测、查错、修改模型。两段测试视频用于正式评分，答案由组织方保存。

## 1. 每段的难度

| 出现顺序 | 数量 | 内容 |
|---|---:|---|
| 清晰 | 4 | 两个数字、两个温度；字较大，保留原始清晰画面 |
| 中等 | 4 | 两个数字、两个温度；小字、轻度模糊和轻微噪声 |
| 困难 | 2 | 一个数字、一个温度；运动模糊或部分遮挡，并有噪声 |
| 无法辨认 | 2 | 一个数字、一个温度；检查是否能正确输出“看不清” |

每段的数值、标牌位置、大小和相机角度随视频变化。

## 2. 下载与解压

在 [v0.3.0 下载页](https://github.com/LWS30/xunyuan-evaluation/releases/tag/v0.3.0)取得两个视频包和校验文件：

```bash
mkdir -p artifacts/downloads
curl -fL https://github.com/LWS30/xunyuan-evaluation/releases/download/v0.3.0/xunyuan-v3-training-videos.zip \
  -o artifacts/downloads/xunyuan-v3-training-videos.zip
curl -fL https://github.com/LWS30/xunyuan-evaluation/releases/download/v0.3.0/xunyuan-v3-test-videos.zip \
  -o artifacts/downloads/xunyuan-v3-test-videos.zip
curl -fL https://github.com/LWS30/xunyuan-evaluation/releases/download/v0.3.0/SHA256SUMS \
  -o artifacts/downloads/SHA256SUMS
(cd artifacts/downloads && sha256sum -c SHA256SUMS)
python -m zipfile -e artifacts/downloads/xunyuan-v3-training-videos.zip datasets/video_v3
python -m zipfile -e artifacts/downloads/xunyuan-v3-test-videos.zip datasets/video_v3
```

解压后有 `train/train01.mp4` 至 `train08.mp4`、`train/reference.json`、`test/test01.mp4` 和 `test02.mp4`，以及 `manifest.json`。

## 3. 单独检查识别项目

```bash
python -m xunyuan_eval read-videos \
  --submission my_team/submission.json --videos datasets/video_v3 \
  --split train --video train01 --output results/train01_predictions.json
python -m xunyuan_eval score-video \
  --predictions results/train01_predictions.json \
  --reference datasets/video_v3/train/reference.json --video train01 \
  --output results/train01_score.json
```

结果列出正确答案、模型读数、是否答对，以及 20 分制成绩。去掉 `--video train01` 可读取和评分全部八段训练视频。

也可以按[首页](../README.md)的一条自测命令，同时生成导航运控与训练识别的 70 分练习成绩。

## 4. 自己换标牌内容

按[内容样例](../datasets/video_v3/content.example.json)填写十二个数值，再生成新视频：

```bash
MUJOCO_GL=egl python -m tools.build_video_v3 \
  --output artifacts/my_videos --private organizer/my_video_answers \
  --content content.json
```

自定义内容用于训练视频，测试内容另行随机生成。每次使用新的输出目录即可保留已有数据。

原来的数字和温度静态图片仍可用于训练，见[图片数据说明](image-datasets.md)。
