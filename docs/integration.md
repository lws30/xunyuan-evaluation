# 测评程序怎么运行

选手提供两个项目，我们提供统一的仿真、观测和视频。程序按清单启动选手代码，再用实际运行记录算分。

## 1. 安装和项目准备

```bash
python -m pip install -e ".[runtime]"
```

地图、机器人、传感器和评分规则在 `challenges/v3/`。两个项目各自的依赖按对应 `AGENT.md` 安装，Agent 执行顺序见[复现步骤](agent-evaluation.md)。

## 2. 导航调用过程

```text
前置图像或雷达点云 + 路线指令 + IMU 和关节状态
    ↓
选手 navigation 项目的运行代码，加载自己的权重
    ↓
16 个腿关节和轮子动作
    ↓
MuJoCo 推进一步，记录位置、姿态、接触、外力和地面摩擦
    ↓
评分器比较轨迹，检查失败情况，计算成绩
```

每个物理步长 0.005 秒，模型每秒调用 50 次，图像和点云每秒更新 10 次。纯雷达项目可直接使用点云，无需启动图像渲染。

每次测试先把机器人置于统一姿态；模型在 `reset` 时清空历史，从时间 0 开始运行。各次测试分别启动项目进程。

每张地图按以下顺序运行：正常路线一次；60、40、20、5 N 各一次；摩擦 0.1、0.2、0.4、0.8 各一次。即每图九次，五图共 45 次。某档失败后，继续单独运行下一档。

## 3. 选手自测

```bash
MUJOCO_GL=egl python -m xunyuan_eval run-submission \
  --submission my_team/submission.json --videos datasets/video_v3 \
  --split train --output results/my_test01
```

这条命令还会运行八段训练视频，将训练识别分与导航运控分放在同一个 `report.json`。`automated_score` 是满分 70 的练习成绩。

只跑一张地图，可加 `--route map01`。检查安装时，可再加 `--max-seconds 3` 缩短每次试跑。

## 4. 组织方正式测试

```bash
MUJOCO_GL=egl python -m xunyuan_eval run-submission \
  --submission team/submission.json --videos datasets/video_v3 \
  --split test --video-reference organizer/video_test_reference.json \
  --seed 20261126 --output results/team01
```

同一批选手使用同一份地图、视频、规则和种子。识别测试的答案由组织方保存。

## 5. 输出文件

```text
results/team01/
  run.json                 运行清单、项目校验值和传感器声明
  report.json              路线、推力、摩擦、识别成绩
  reference.json           本次规则快照
  video_predictions.json   模型读出的视频结果
  logs/                    两个项目的标准错误日志
  map01/
    normal/
      states.json          每秒摘要和结束原因
      physics.jsonl        每个物理步的真实状态
      forces.json          施力记录
      result.json          本次运行结果
    force_60/
    force_40/
    force_20/
    force_5/
    friction_0.1/
    friction_0.2/
    friction_0.4/
    friction_0.8/
```

`map02` 至 `map05` 结构相同。记录格式见[成绩和记录说明](protocol.md)。模型出现错误时保留日志和已完成测试的结果，未获得的分数计 0。

## 6. 填入报告分

```bash
python -m xunyuan_eval add-report-score \
  --report results/team01/report.json --score 27 \
  --output results/team01/final_report.json
```

`final_score` 为自动分加报告分，满分 100。

## 7. 生成新地图和视频

```bash
python -m tools.build_challenge_v3 \
  --calibration challenges/v3/calibration.json --seed 42317 \
  --output organizer/new_challenge
MUJOCO_GL=egl python -m tools.build_video_v3 \
  --output artifacts/new_videos --private organizer/new_video_answers
```

地图保持同样的转弯顺序，直道路段长度随机为 5 至 8 米。生成工具同时更新参考轨迹。视频工具把标牌放在右墙，再移动相机采集，训练答案放入训练目录，测试答案放入组织方指定目录。
