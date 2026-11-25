# 选手提交什么

提交一个压缩包，里面是两个 ONNX 模型、一份报告和一份文件清单。

```text
my_team/
  submission.json
  policy.onnx
  reader.onnx
  report.pdf
```

## 1. 两个模型分别做什么

| 文件 | 输入 | 输出 |
|---|---|---|
| `policy.onnx` | 前置相机画面、转弯任务，可使用 IMU 和关节状态 | 12 个腿关节和 4 个轮子的动作 |
| `reader.onnx` | 右侧视频画面 | 标牌位置、数字或温度、可信度、是否看得清 |

导航和运控可以在模型内部使用不同网络，导出时合在 `policy.onnx` 中。模型文件内包含权重，输入输出按[模型接口](model-interface.md)准备。

报告保存为 `report.pdf`。

## 2. 文件清单怎么写

`submission.json` 内容如下：

```json
{
  "schema_version": "2.0",
  "team": "你的队伍名称",
  "policy": "policy.onnx",
  "reader": "reader.onnx",
  "report": "report.pdf"
}
```

文件名可以改，清单中的路径跟着改。路径以 `submission.json` 所在文件夹为起点。

## 3. 提交前检查

```bash
python -m xunyuan_eval check-submission --submission my_team/submission.json
```

程序检查模型能否加载、输入输出名称和大小是否正确，以及报告文件是否存在。遇到问题时，会指出哪一项需要调整。

先试跑一张地图：

```bash
MUJOCO_GL=egl python -m xunyuan_eval run-submission \
  --submission my_team/submission.json --route map01 \
  --output artifacts/my_map01
```

这会运行这张图的路线和扰动测试。打开结果目录里的 `report.json` 看成绩；各次运行的 `states.json` 记录每秒的状态。

## 4. 打包

```bash
python -m xunyuan_eval package-models \
  --submission my_team/submission.json --output artifacts/team_submission.zip
```

打包工具会统一文件名，写入文件校验值。把生成的 `team_submission.zip` 按赛事指定渠道提交。

我们解压后运行你的模型，保存仿真状态和识别结果，再计算成绩。
