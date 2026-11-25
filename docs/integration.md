# 测评程序怎么运行

选手准备模型，我们用统一的地图、S10 模型和视频运行它们。

## 1. 准备环境

在仓库根目录安装：

```bash
python -m pip install -e ".[runtime]"
```

本次使用 Python 3.11、MuJoCo 3.13.0、ONNX Runtime 1.30.0 运行检查。

赛道和机器人在 `challenges/v2/`，转弯任务在 `challenges/v2/tasks/`，视频按[下载说明](datasets.md)放进 `datasets/video_v2/`。

## 2. 解压选手文件

```bash
python -m zipfile -e team_submission.zip team
python -m xunyuan_eval check-submission --submission team/submission.json
```

选手包里包含 `policy.onnx`、`reader.onnx`、`report.pdf`、`submission.json`。

## 3. 运行导航和运控

程序从每张图的起点出发，先测一次路线，再从低到高测扰动。

```text
前置画面、转弯指令和传感器状态
    ↓
选手的 policy.onnx
    ↓
腿关节和轮子动作
    ↓
MuJoCo 推进一步，记录位置、姿态、接触和外力
    ↓
评分器比较轨迹、检查失败情况、计算得分
```

程序在初始化阶段让机器人进入统一姿态，再从时间 0 开始测试。模型的记忆和上一次动作也在每次测试开始时清零。

每个物理步都检查碰撞和姿态，同时每秒保存一次状态摘要。路线结束、碰撞、摔倒、越界或超时都会结束这次运行。

## 4. 运行视频识别

识别模型逐帧读取测试视频，输出标牌位置和文字。评分器再和组织方保存的答案比较。

```bash
MUJOCO_GL=egl python -m xunyuan_eval run-submission \
  --submission team/submission.json --output results/team01 \
  --videos datasets/video_v2 \
  --video-reference organizer/video_test_reference.json --seed 20261125
```

每批选手使用相同种子，便于比较扰动测试结果。种子写进运行清单。

视频识别出现模型错误时，这部分记 0 分，并在报告中写明原因；已经完成的路线和扰动成绩保留。

## 5. 看输出

```text
results/team01/
  run.json                 运行清单和模型校验值
  report.json              路线、扰动、识别成绩
  video_predictions.json   模型读出的视频结果
  map01/
    normal/
      states.json          每秒摘要和结束原因
      physics.jsonl        每个物理步的详细状态
      forces.json          施力记录
      result.json          本次运行结果
    force_0.5/
    ...
```

`map02` 至 `map05` 的结构相同。每个档位单独初始化、单独记录；失败后停止该图更高档的扰动测试。

只检查安装时，可以加 `--route map01 --max-seconds 3` 缩短试跑。

## 6. 填入报告分

```bash
python -m xunyuan_eval add-report-score \
  --report results/team01/report.json --score 27 \
  --output results/team01/final_report.json
```

生成的 `final_report.json` 中，`final_score` 是自动分与报告分之和，满分 100。

## 7. 重新生成地图和视频

```bash
python -m tools.build_challenge_v2 --output artifacts/new_maps
MUJOCO_GL=egl python -m tools.build_video_v2 \
  --output artifacts/new_videos --private organizer/new_video_answers
```

地图生成工具使用仓库自带的机器人资源。视频生成工具把小标牌放在走廊右墙，再移动相机采集画面；训练答案随训练视频保存，测试答案保存在指定的组织方目录。

## 8. 换一组路段长度测试

公开五图用于练习。也可以把直道路段长度随机设为 5 至 8 米，并保留原来的转弯顺序。模型通过前置画面发现路口，再执行该路口对应的指令。

```bash
python -m tools.build_challenge_v2 --output organizer/round01 --seed 42317
MUJOCO_GL=egl python -m xunyuan_eval run-submission \
  --submission team/submission.json --challenge organizer/round01 \
  --output results/team01_round01 --videos datasets/video_v2 \
  --video-reference organizer/video_test_reference.json --seed 20261125
```

同一批选手使用同一份生成地图。地图里的参考路线和评分配置会一起更新。
