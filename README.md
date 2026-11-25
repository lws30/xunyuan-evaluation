# 巡渊 S10 比赛：公开自评工具

选手可以用同一份公开配置校验运行记录、复算通行/导航/停靠成绩，并生成带文件校验值的自评提交包。核心工具仅依赖 Python 3.10+ 标准库，可断网运行。

**当前为开发自评 v0.1，评分配置仍为候选口径。** 运行本工具得到的是公开练习成绩。正式测试由赛事方使用冻结规则、独立记录与正式场景计算。

## 1. 五分钟跑通自评流程

```bash
git clone https://github.com/LWS30/xunyuan-evaluation.git
cd xunyuan-evaluation

# 生成用于检查文件格式和评分逻辑的合成样例
python3 -m xunyuan_eval demo --output artifacts/demo

# 校验文件格式、时间戳、版本和策略一致性
python3 -m xunyuan_eval validate \
  --run artifacts/demo/run.json \
  --reference artifacts/demo/reference.json

# 初赛自评；查看 report.json 中的逐试次原因
python3 -m xunyuan_eval evaluate \
  --run artifacts/demo/run.json \
  --reference artifacts/demo/reference.json \
  --output artifacts/demo/report.json

# 生成自评提交包；打包时重新评分，不采用手改的 report.json
python3 -m xunyuan_eval prepare-submission \
  --run artifacts/demo/run.json \
  --reference artifacts/demo/reference.json \
  --output artifacts/submission.zip
```

合成样例的预期结果为自动评分 **70/70**，初赛报告项 **30 分待人工评审**，`final_score` 为 `null`。`demo` 只验证软件协议与评分逻辑，不运行机器人或物理仿真，其成绩不能证明 S10 的通行能力。

命令成功返回 0；输入格式错误、文件缺失或版本不匹配返回 2。有效的失败试次仍能正常出报告，退出码不会被误当成通过率。

## 2. 用自己的运行记录自评

1. 在公开开发场景中运行自己的算法，按 [接入说明](docs/integration.md)从模拟器/评测进程记录真实状态。
2. 每个独立试次、每轮连续任务分别保存一份 JSONL 轨迹，创建 [run.json 清单](docs/protocol.md)。
3. 使用与场景一致的公开参考配置校验和评分：

```bash
python3 -m xunyuan_eval evaluate \
  --run my_run/run.json \
  --reference references/public_dev_v3_candidate.json \
  --stage preliminary \
  --output artifacts/my_report.json
```

`references/public_dev_v3_candidate.json` 包含 21 个独立通行试次、3 轮共 15 个导航事件和 12 个停靠事件，使用公开 V3 约 50 米开发路线的几何判据。它不对应另一个 12 点长路网演示，也不能直接用于其他地图。完整场景、机器人模型和算法由相应开发环境提供；本仓库负责记录协议和离线裁判，不启动算法容器或生成赛道。

该配置要求评测侧每个物理步记录一次，名义间隔 0.005 秒，最大允许间隔 0.0075 秒。发生缺口后不跨越缺口推断成功；连续任务保留此前有效事件，之后事件不计分。

## 3. 评分覆盖什么

| 项目 | 自动计算方式 | 满分 |
|---|---|---:|
| 直道与转弯 | 共 6 次；合格数 / 6 × 5 | 5 |
| 上坡与下坡 | 共 6 次；合格数 / 6 × 5 | 5 |
| 上楼梯 | 共 3 次；合格数 / 3 × 5 | 5 |
| 下楼梯 | 共 3 次；合格数 / 3 × 5 | 5 |
| 摩擦变化 | 共 3 次；合格数 / 3 × 5 | 5 |
| 自主导航 | 15 个事件；首次正确出口数 / 15 × 25 | 25 |
| 到点停靠 | 12 个事件；连续稳定窗口合格数 / 12 × 20 | 20 |
| 自动评分合计 | 保留未完成、失败和缺失项的固定分母 | **70** |

通行成功需要整机碰撞外廓通过出口，不能只用机身中心越线。导航按有方向、有限宽度的出口门判断，走错出口后折返不会恢复该事件得分。停靠按真实位置、朝向、速度和角速度连续保持判断，不能只发送零速度指令。

初赛另外 30 分为方案报告；决赛另外 25 分为巡检记录回看、5 分为部署与复现。它们显示在 `pending_manual` 中，不由本工具自动填满。当前没有独立的读数或测温加分。详细口径与待冻结项目见 [规则说明](docs/rules.md)。

## 4. 输出与提交

`report.json` 包括分项成绩、固定分母、逐事件通过/失败原因、规则版本、策略标识和输入文件 SHA-256。分数保留计算精度，展示时可统一保留两位小数。

`submission.zip` 包含 `run.json`、本次参考配置、所引用的轨迹、重算的 `report.json` 和 `submission.json` 校验清单。它是**自评记录包**；正式交付中的算法 Docker 镜像和报告仍按赛事说明提交。打包命令只收集清单直接引用的轨迹，不递归上传整个工作目录。

这个发布版本没有联网提交、账号系统或排行榜后端；可将代码链接和自评记录包直接发给选手。若以后建设在线评测站，应在独立评测进程中重算成绩，不能直接采用上传报告里的分数。

## 5. 可选的离线读数诊断

```bash
python3 -m xunyuan_eval readings \
  --predictions examples/reading_predictions.json \
  --reference examples/reading_reference.json \
  --output artifacts/reading_report.json
```

普通数字按原始字符串比较，保留前导零、负号和小数点；温度屏按单位和误差容差比较；不可读样本需要明确拒识原因。样例为独立合成示例，不含正式测试答案。读数诊断结果的 `competition_score` 为 `null`，RGB 读屏也不等同于红外物理测温。

## 6. 官方 S10 baseline

机器人基础代码、策略与安装方法直接从云深处官方获取：

- [S10 SDK 与部署说明](https://github.com/DeepRoboticsLab/sdk_deploy/blob/main/src/S10_sdk_deploy/README.md)
- [S10 强化学习训练仓库](https://github.com/DeepRoboticsLab/rl_training)
- [S10 机器人模型仓库](https://github.com/DeepRoboticsLab/deep_robotics_model)

本仓库不随附参赛队伍的控制器、训练权重、个人实验轨迹或机器专用路径。

## 7. 目录与测试

```text
xunyuan_eval/       命令行、输入校验、裁判、记录器和打包工具
references/         公开 V3 候选几何判据与独立协议样例
examples/           合成读数输入示例
docs/               记录协议、接入方法、规则和发布说明
tests/              评分与格式边界测试
docs/ci-workflow.example.yml  多版本 Python CI 模板
```

```bash
python3 -m unittest discover -s tests -v
```

核心测试无需 GPU、MuJoCo 或模型下载。可选 MuJoCo 记录适配器需要调用方安装 MuJoCo/NumPy；使用方法见接入文档。

当前发布账号授权不含 GitHub `workflow` 权限，因此工作流以模板形式提供，尚未启用 GitHub Actions。仓库维护者取得相应权限后，可将模板复制到 `.github/workflows/test.yml` 启用。代码已分别在标准 Python 环境和包含 MuJoCo 的环境执行测试。

## 8. 参考组织方式

参考 [DriveLM challenge](https://github.com/OpenDriveLab/DriveLM/tree/main/challenge) 将样例、离线评测和提交准备分别公开的组织方式，以及 [AGC2024 评测 Space](https://huggingface.co/spaces/AGC2024/driving-with-language-official) 的提交入口形式。本实现针对巡渊任务独立编写，没有复制其评测实现，也没有沿用其语言模型评分或比赛数据。

代码采用 MIT 许可。问题与复现实例可通过本仓库 Issues 反馈，请附参考配置版本、命令和最小化输入。
