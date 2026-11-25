# 选手提交什么

提交两个完整项目文件夹和一份报告。权重格式由选手选择，可以用 PyTorch、ONNX 或其他框架。

```text
my_team/
  submission.json
  navigation/
    AGENT.md
    run.py
    requirements.txt
    weights/model.pt
    config.yaml
  recognition/
    AGENT.md
    run.py
    requirements.txt
    weights/model.pt
    config.yaml
  report.pdf
```

`run.py` 是运行入口的例子，选手可以换名称或使用其他语言。清单中的 `command` 指向实际入口。模型用到的配置、预处理和后处理代码一起放入对应文件夹。

## 1. 每个 AGENT.md 写什么

- 使用的 Python 或运行环境版本。
- 安装依赖的命令，包括模型需要的额外文件。
- 权重和配置的路径。
- 启动命令、输入输出处理方法。
- 一条可执行的检查命令，以及预期结果。

Agent 按这份文件安装、启动并复现项目。参考[复现步骤](agent-evaluation.md)。

## 2. 文件清单

`submission.json` 示例：

```json
{
  "schema_version": "3.0",
  "team": "你的队伍名称",
  "navigation": {
    "directory": "navigation",
    "command": ["{python}", "run.py"],
    "requirements": "requirements.txt",
    "weights": ["weights/model.pt"],
    "sensors": ["front_rgb"]
  },
  "recognition": {
    "directory": "recognition",
    "command": ["{python}", "run.py"],
    "requirements": "requirements.txt",
    "weights": ["weights/model.pt"]
  },
  "report": "report.pdf"
}
```

`weights` 可以列出多个文件，文件扩展名自由。目录和文件路径以各自项目目录为起点，`report` 以清单所在目录为起点。

`{python}` 优先使用项目自己的 `.venv/bin/python`，存在时自动选择；否则使用运行测评器的 Python。两个项目可以分别安装自己的依赖。

导航 `sensors` 可以填：`["front_rgb"]`、`["lidar_points"]` 或 `["front_rgb", "lidar_points"]`。程序按声明提供视觉、雷达或融合输入，并在成绩中记录。

## 3. 运行检查

```bash
python -m xunyuan_eval check-submission --submission my_team/submission.json
python -m xunyuan_eval check-submission --submission my_team/submission.json --smoke
```

第一条检查文件、权重、依赖说明和两份 `AGENT.md`。第二条实际启动两个项目，各发送一次输入，检查能否返回动作和识别结果。

进程通信格式见[运行接口](model-interface.md)。生成完整示例：

```bash
python -m tools.make_project_example --output artifacts/example_team
```

## 4. 自测和打包

```bash
MUJOCO_GL=egl python -m xunyuan_eval run-submission \
  --submission my_team/submission.json --videos datasets/video_v3 \
  --split train --output results/my_test01
python -m xunyuan_eval package-models \
  --submission my_team/submission.json --output artifacts/team_submission.zip
```

结果中的 `automated_score` 是本次 70 分制练习成绩。只跑导航时可以省略 `--videos`，查看 `navigation_control_score`，满分 50。

打包工具保留两个项目里的代码、权重、配置、依赖和 `AGENT.md`，并记录文件校验值。`.venv`、`.git` 和 Python 缓存留在本机。把 `team_submission.zip` 按赛事指定渠道提交。
