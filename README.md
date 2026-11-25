# 巡渊 S10 测评工具

选手提交两个 ONNX 模型和一份 PDF 报告。测评程序在五张赛道上运行导航运控模型，再用测试视频检查识别模型，最后生成成绩 JSON。

当前版本：**v0.2.0**。

## 1. 分数怎么算

| 项目 | 分值 | 怎么测 |
|---|---:|---|
| 导航和运控 | 50 | 路线 30 分：五张图各走完 5 个路口并返回；扰动 20 分：每图按 0.5、1、3、5 牛依次测试 |
| 视频识别 | 20 | 识别两段测试视频中的数字和温度 |
| 报告 | 30 | 评委评分后填入总成绩 |

每张地图的路线满分 6 分：5 个路口各 1 分，返程 1 分。按轨迹离规定路线有多远扣分；撞墙、摔倒或越界时，本次测试失败。详细扣分表见[评分规则](docs/rules.md)。

## 2. 我们给选手什么

- 五张 MuJoCo 赛道，包含 S10 模型、前置相机和右侧相机。
- 每张图一份 JSON 任务，写明去程、掉头和返程怎么走。
- 十段右侧视角视频，每段 10 分钟；8 段训练、2 段测试。
- 模型输入输出格式、提交检查工具和本地试跑命令。

| 地图 | 去程五个路口 | 任务文件 |
|---|---|---|
| [地图 1](challenges/v2/maps/map01.png) | 左、直、右、左、右 | [map01.json](challenges/v2/tasks/map01.json) |
| [地图 2](challenges/v2/maps/map02.png) | 直、直、左、右、左 | [map02.json](challenges/v2/tasks/map02.json) |
| [地图 3](challenges/v2/maps/map03.png) | 右、左、直、右、直 | [map03.json](challenges/v2/tasks/map03.json) |
| [地图 4](challenges/v2/maps/map04.png) | 左、右、右、直、左 | [map04.json](challenges/v2/tasks/map04.json) |
| [地图 5](challenges/v2/maps/map05.png) | 直、左、右、左、直 | [map05.json](challenges/v2/tasks/map05.json) |

到终点后掉头，按任务文件中的返程指令回到起点。

机器人用前置摄像头发现路口，再按顺序执行任务里的指令。例如任务写着“左、直、右”，就表示看到第一个路口左转，看到第二个路口直行，看到第三个路口右转。模型自己判断何时到达路口。

## 3. 选手提交什么

```text
team_submission.zip
  submission.json   队伍名称和文件清单
  policy.onnx       导航和运控模型
  reader.onnx       视频识别模型
  report.pdf        方案报告
```

`policy.onnx` 读取前置图像和路线指令，输出腿关节和轮子的动作。`reader.onnx` 读取右侧视频画面，输出标牌位置、读数和“是否看得清”。每个 ONNX 文件内包含运行所需的权重。

按[提交说明](docs/submission.md)准备好文件后，先检查，再打包：

```bash
python -m xunyuan_eval check-submission --submission my_team/submission.json
python -m xunyuan_eval package-models \
  --submission my_team/submission.json --output artifacts/team_submission.zip
```

## 4. 本地怎么试

使用 Python 3.11，安装程序和仿真依赖：

```bash
git clone https://github.com/LWS30/xunyuan-evaluation.git
cd xunyuan-evaluation
python -m pip install -e ".[runtime]"
```

先生成一组用于检查安装和接口的示例文件。这个示例让机器人原地站着：

```bash
python -m tools.make_v2_interface_example --output artifacts/interface_example
MUJOCO_GL=egl python -m xunyuan_eval run-submission \
  --submission artifacts/interface_example/submission.json \
  --route map01 --max-seconds 3 --output artifacts/first_run
```

打开 `artifacts/first_run/report.json` 看结果。每秒的位置、姿态和碰撞状态保存在各次运行的 `states.json`，详细记录在 `physics.jsonl`。

换成自己的模型后，去掉 `--route` 和 `--max-seconds`，就会运行五张地图和四档扰动测试。模型具体格式见[模型接口](docs/model-interface.md)。

## 5. 视频怎么训练和检查

[下载视频](docs/datasets.md)后，用自己的识别模型读取一段训练视频：

```bash
python -m xunyuan_eval read-videos \
  --model my_team/reader.onnx --videos datasets/video_v2 \
  --split train --video train01 --output artifacts/train01_predictions.json
python -m xunyuan_eval score-video \
  --predictions artifacts/train01_predictions.json \
  --reference datasets/video_v2/train/reference.json --video train01 \
  --output artifacts/train01_score.json
```

查看错了哪些标牌，修改模型后再试。每段视频有 6 个数字牌、6 个温度屏，字比较小，包含模糊、遮挡和完全看不清的情况。

## 6. 我们怎么给选手测评

解压选手的提交包后，运行：

```bash
MUJOCO_GL=egl python -m xunyuan_eval run-submission \
  --submission team/submission.json --output results/team01 \
  --videos datasets/video_v2 \
  --video-reference organizer/video_test_reference.json --seed 20261125
```

程序负责运行模型、记录轨迹、检查碰撞、施加扰动和计算成绩。同一批选手使用同一组地图、参数和随机种子。测试视频的答案文件由组织方保存。

评委给报告打分后，例如 27 分：

```bash
python -m xunyuan_eval add-report-score \
  --report results/team01/report.json --score 27 \
  --output results/team01/final_report.json
```

自动分加上报告分，就是 100 分制总成绩。更多运行细节见[测评程序说明](docs/integration.md)。

## 7. 文件和检查命令

```text
challenges/v2/      五张赛道、S10模型、转弯任务和评分参数
xunyuan_eval/      模型运行、记录和评分程序
datasets/video_v2/ 视频清单、训练答案和下载说明
tools/             生成地图、视频和示例模型的工具
tests/             自动测试
docs/              提交、模型接口、评分和数据说明
```

```bash
python -m unittest discover -s tests -v
python -m tools.check_v2_physics --output artifacts/physics_check.json
```

想先看打分文件的格式，可以生成一组理想轨迹和识别结果：

```bash
python -m xunyuan_eval demo-v2 --output artifacts/scoring_example
python -m xunyuan_eval score-challenge \
  --run artifacts/scoring_example/run.json \
  --reference artifacts/scoring_example/reference.json \
  --video-reference artifacts/scoring_example/video_reference.json \
  --output artifacts/scoring_example/report.json
```

这组生成记录的预期得分是路线 30、扰动 20、识别 20，报告分等待评委填写。
