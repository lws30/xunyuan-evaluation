# 巡渊 S10 比赛：公开自评工具

选手可以用同一份公开配置校验运行记录、复算通行/导航/停靠成绩，并生成带文件校验值的自评提交包。核心工具仅依赖 Python 3.10+ 标准库，可断网运行。

**当前为开发自评 v0.1.1，评分配置仍为候选口径。** 运行本工具得到的是公开练习成绩。正式测试由赛事方使用冻结规则、独立记录与正式场景计算。

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

仓库提供两组带标注的公开图片：

| 数据 | 内容 | 获取方式 |
|---|---|---|
| [数字牌与温度屏](datasets/readings_v3/) | V3 开发场景的 6 张数字牌、6 张温度屏，附读数、单位和图片路径 | 随仓库提供 |
| [温度读屏数据集](datasets/temperature_v3/) | 15,000 条样本，每条含完整面板和数字行裁剪，共 30,000 张图片；训练 / 验证 / 测试为 12,000 / 1,500 / 1,500 条 | 完整图片见 [v0.1.1 Release](https://github.com/LWS30/xunyuan-evaluation/releases/tag/v0.1.1)，仓库附完整标注和 30 条图片样例 |

温度数据包含正常、遮挡、模糊、遮挡叠加模糊和不可读五种情况；同一温度值及其所有增强只属于一个数据划分。两组图片均为本地生成的合成显示图，用于数字和温度读屏练习。数据字段、下载校验和预测文件格式见[数据集说明](docs/datasets.md)。

可先用仓库自带的温度图片样例导出诊断参考：

```bash
python3 -m xunyuan_eval reading-reference \
  --dataset datasets/temperature_v3/sample --split test \
  --output artifacts/temperature_sample_reference.json
```

用自己的 OCR 程序读取图片，输出预测值或拒识原因后，再运行 `readings` 对照标注计算结果。下面的命令使用原有 JSON 协议样例检查诊断流程：

```bash
python3 -m xunyuan_eval readings \
  --predictions examples/reading_predictions.json \
  --reference examples/reading_reference.json \
  --output artifacts/reading_report.json
```

普通数字按原始字符串比较，保留前导零、负号和小数点；温度屏按单位和误差容差比较；不可读样本需要明确拒识原因。`readings` 对照预测 JSON 和参考标注计算正确数，OCR 模型由使用者接入。诊断结果的 `competition_score` 为 `null`；温度图片的任务是读取屏幕显示值，红外物理测温需另行接入测温设备。

## 6. 官方 S10 baseline

机器人基础代码、策略与安装方法直接从云深处官方获取：

- [S10 SDK 与部署说明](https://github.com/DeepRoboticsLab/sdk_deploy/blob/main/src/S10_sdk_deploy/README.md)
- [S10 强化学习训练仓库](https://github.com/DeepRoboticsLab/rl_training)
- [S10 机器人模型仓库](https://github.com/DeepRoboticsLab/deep_robotics_model)

本仓库不随附参赛队伍的控制器、训练权重、个人实验轨迹或机器专用路径。

## 7. 目录、依赖与测试

```text
xunyuan_eval/       命令行、输入校验、裁判、记录器和打包工具
references/         公开 V3 候选几何判据与独立协议样例
examples/           合成读数输入示例
datasets/           数字与温度图片、标注、预览及完整数据下载信息
docs/               记录协议、接入方法、规则和发布说明
tests/              评分与格式边界测试
docs/ci-workflow.example.yml  多版本 Python CI 模板
```

### 离线评分需要什么

已有运行轨迹时，只需 Python 3.10+ 即可执行格式校验、离线评分和提交打包；这些步骤只读取记录文件，因此无需 GPU、MuJoCo 或模型下载。运行机器人策略、生成仿真轨迹和用 OCR 模型识别图片，各自需要对应的运行环境。

### 真实仿真如何记录、判断摔倒并评分

1. 在包含 S10 模型和赛道的仿真环境中运行参评策略。评测进程每个物理步从模拟器读取真实状态，并写入轨迹；算法仅接收规定的传感器和任务输入。
2. 使用 MuJoCo 时，可接入 `MuJoCoSampler` 和 `TraceRecorder`。采样器读取机身姿态、实际速度、整机碰撞外廓及接触信息；场景接入代码负责指定允许接触的地形与连杆、边界检查和动作合法性检查。安装 `mujoco`、`numpy` 后按[接入说明](docs/integration.md)配置。
3. 评分器逐帧检查这些状态。当前公开候选配置以横滚或俯仰绝对值超过 **45°** 作为跌倒判据，同时检查禁止接触、越界、非法动作、人工接管、超时和采样缺口。独立通行试次遇到安全失败记为未通过；连续任务保留失败前已完成的有效事件，之后事件不计分。具体原因写入 `report.json`。
4. 缺少姿态等必需字段或引用的轨迹文件时，校验报错；缺少整项试次时，该项按 0 分保留分母。评分取决于所提供的记录，正式评测应由赛事方独立运行并采集轨迹。

因此，判断 S10 是否摔倒需要真实仿真或实机的状态记录。合成 `demo` 的 70/70 用于检查文件协议和评分逻辑；完整 S10 赛道能力需要接入模型、场景和策略后另行验证。

### 测试命令与验证范围

```bash
# 核心测试：协议、评分边界、读数诊断、数据集接入和提交打包
python3 -m unittest discover -s tests -v

# 可选 MuJoCo 适配器测试：需先安装 MuJoCo 和 NumPy
python3 -m unittest discover -s tests -p test_mujoco_adapter.py -v

# 真实物理步进检查：刚体在重力下倾倒，记录姿态并验证跌倒判定
python3 -m examples.mujoco_fall_check --output artifacts/mujoco_fall_check
```

未安装 MuJoCo 时，适配器测试会标记为 `skipped`；核心测试照常执行。物理步进检查使用简单刚体，验证从模拟器采样到安全判定的链路。当前验证范围包括核心测试、适配器测试、物理步进检查、合成样例评分和提交包复算，完整 S10 赛道联调仍需在对应仿真环境完成。

`docs/ci-workflow.example.yml` 提供 Python 3.10–3.13 的自动测试模板。需要启用 GitHub Actions 时，将其放到 `.github/workflows/test.yml`；当前仓库保留模板供维护者使用。
