# Agent 怎样复现和测评选手项目

输入是选手的完整提交包。目标是安装两个项目，启动推理程序，在统一地图和视频中运行，再生成成绩。

## 1. 读取说明

解压到 `team/`，阅读 `submission.json`、`navigation/AGENT.md`、`recognition/AGENT.md`，确认权重和配置已经放齐。安装命令和运行环境按对应项目说明执行。

## 2. 分别安装两个项目

Python 项目可以分别建立环境，例如：

```bash
python3.11 -m venv team/navigation/.venv
team/navigation/.venv/bin/python -m pip install -r team/navigation/requirements.txt
python3.11 -m venv team/recognition/.venv
team/recognition/.venv/bin/python -m pip install -r team/recognition/requirements.txt
```

清单中使用 `{python}` 时，测评器优先调用各项目的 `.venv/bin/python`。其他语言或环境由选手在 `command` 和 `AGENT.md` 中给出启动方法。

## 3. 检查文件和推理

```bash
python -m xunyuan_eval check-submission --submission team/submission.json --smoke
```

预期输出 `valid=true` 和 `smoke_passed=true`。遇到依赖或入口问题，按项目的 `AGENT.md` 排查，并保存运行命令和错误记录。

## 4. 先运行练习评测

```bash
MUJOCO_GL=egl python -m xunyuan_eval run-submission \
  --submission team/submission.json --videos datasets/video_v3 \
  --split train --output results/team_practice
```

结果包含导航运控 50 分、训练视频识别 20 分和各项错误。模型标准错误日志保存在 `results/team_practice/logs/`。

## 5. 运行正式评测

组织方准备统一的地图、视频答案和种子后执行：

```bash
MUJOCO_GL=egl python -m xunyuan_eval run-submission \
  --submission team/submission.json --challenge organizer/challenge \
  --videos datasets/video_v3 --split test \
  --video-reference organizer/video_test_reference.json \
  --seed 20261126 --output results/team_final
```

保存 `run.json`、`report.json`、项目日志和仿真记录。运行清单包含提交代码、权重、依赖文件和输入数据的校验值，以及传感器配置。

## 6. 填入报告分

```bash
python -m xunyuan_eval add-report-score \
  --report results/team_final/report.json --score 27 \
  --output results/team_final/final_report.json
```

最终交付成绩文件、运行命令和复现日志，便于核查每项分数。
