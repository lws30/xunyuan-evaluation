# 巡渊 S10 比赛评分工具

先让机器人在仿真里跑一遍，记录它的位置、姿态、速度和碰撞情况。这个工具读取记录，计算通行、导航和停靠的分数，再把记录和成绩打成提交包。

当前版本：**v0.1.1**。需要 Python 3.10 或以上版本。

## 1. 先用样例跑一遍

```bash
git clone https://github.com/LWS30/xunyuan-evaluation.git
cd xunyuan-evaluation

# 生成样例记录
python3 -m xunyuan_eval demo --output artifacts/demo

# 检查记录格式
python3 -m xunyuan_eval validate \
  --run artifacts/demo/run.json \
  --reference artifacts/demo/reference.json

# 计算成绩
python3 -m xunyuan_eval evaluate \
  --run artifacts/demo/run.json \
  --reference artifacts/demo/reference.json \
  --output artifacts/demo/report.json

# 打包记录和成绩
python3 -m xunyuan_eval prepare-submission \
  --run artifacts/demo/run.json \
  --reference artifacts/demo/reference.json \
  --output artifacts/submission.zip
```

样例记录由程序生成，用来熟悉使用方法。预期自动得分为 **70/70**，另外 **30 分由人工评审方案报告**。

运行后打开 `artifacts/demo/report.json`，可以看到每项得分和通过、失败的原因。打包结果在 `artifacts/submission.zip`。

## 2. 给自己的机器人算分

1. 在仿真程序里加入记录器，每个物理步保存一次机器人状态，具体代码见[接入方法](docs/integration.md)。
2. 每次测试保存一份 JSONL 文件。JSONL 就是一行一条状态记录。再用 `run.json` 列出这些文件，格式见[运行记录说明](docs/protocol.md)。
3. 选择与赛道配套的规则文件，运行评分命令：

```bash
python3 -m xunyuan_eval evaluate \
  --run my_run/run.json \
  --reference references/public_dev_v3_candidate.json \
  --stage preliminary \
  --output artifacts/my_report.json
```

仓库中的规则文件对应 V3 约 50 米开发路线，包含 21 次通行测试、15 次路口选择和 12 次停靠。文件中写着出口的位置、方向和宽度，以及停靠点和时间限制。换赛道时，要一起更新这些配置和 `reference_id`。

这份配置要求每 **5 毫秒**记录一次状态。相邻两条记录间隔超过 **7.5 毫秒**时，评分会停在记录中断的位置。

## 3. 分数怎么算

| 项目 | 计算方法 | 满分 |
|---|---|---:|
| 直道与转弯 | 通过次数 ÷ 6 × 5 | 5 |
| 上坡与下坡 | 通过次数 ÷ 6 × 5 | 5 |
| 上楼梯 | 通过次数 ÷ 3 × 5 | 5 |
| 下楼梯 | 通过次数 ÷ 3 × 5 | 5 |
| 摩擦变化 | 通过次数 ÷ 3 × 5 | 5 |
| 自主导航 | 首次选对出口的次数 ÷ 15 × 25 | 25 |
| 到点停靠 | 合格次数 ÷ 12 × 20 | 20 |
| 自动评分合计 | | **70** |

- **通行**：整台机器人通过出口，并在规定时间内安全完成。
- **导航**：每个路口看第一次选的出口。选错后可以折返继续走，该路口得 0 分。
- **停靠**：停在目标附近，朝向正确，并连续保持低速 2 秒。具体数值见[评分规则](docs/rules.md)。

少跑一次测试，那次按 0 分计算，总次数保持不变。

初赛剩余 30 分由人工评审方案报告。决赛剩余 30 分中，25 分评审巡检记录，5 分评审部署与复现。报告里的 `pending_manual` 列出待人工评审的项目。

## 4. 结果在哪里

| 文件 | 内容 |
|---|---|
| `report.json` | 总分、分项成绩、每项通过或失败的原因、规则版本和文件校验值 |
| `submission.zip` | 运行清单、规则文件、运行记录、重算的成绩和文件清单 |

提交包会收集 `run.json` 引用的运行记录，并重新计算成绩。按赛事提供的提交方式交付这个包；算法镜像和方案报告也按赛事要求提交。

## 5. 数字和温度图片怎么用

| 数据 | 内容 | 下载位置 |
|---|---|---|
| [数字牌和温度屏](datasets/readings_v3/) | 6 张数字牌、6 张温度屏，附正确答案 | 仓库内 |
| [温度图片数据集](datasets/temperature_v3/) | 15,000 条样本，每条有完整面板和数字裁剪图，共 30,000 张图片 | [Release 下载页](https://github.com/LWS30/xunyuan-evaluation/releases/tag/v0.1.1) |

图片由程序绘制，包含清晰、遮挡、模糊、遮挡加模糊和完全看不清五种情况。温度数据按训练、验证、测试分成 12,000、1,500、1,500 条，仓库还带了 30 条图片样例。

OCR 就是把图片上的字符读成文字。先用自己的 OCR 程序识别图片，保存结果，再让工具和正确答案比较。完整步骤见[图片使用说明](docs/datasets.md)。

先给仓库自带的温度图片样例生成答案文件：

```bash
python3 -m xunyuan_eval reading-reference \
  --dataset datasets/temperature_v3/sample --split test \
  --output artifacts/temperature_sample_reference.json
```

也可以先用下面的现成答案和预测结果，熟悉比较命令：

```bash
python3 -m xunyuan_eval readings \
  --predictions examples/reading_predictions.json \
  --reference examples/reading_reference.json \
  --output artifacts/reading_report.json
```

数字按文字逐字比较，例如 `00127` 和 `127` 算不同结果。温度按数值和单位比较，默认允许 0.1 ℃ 误差。图片看不清时，结果中写明原因。这项结果单独显示识别正确数。

## 6. S10 模型和基础程序

云深处官方提供机器人模型、训练代码和部署方法：

- [S10 SDK 与部署说明](https://github.com/DeepRoboticsLab/sdk_deploy/blob/main/src/S10_sdk_deploy/README.md)
- [S10 强化学习训练代码](https://github.com/DeepRoboticsLab/rl_training)
- [S10 机器人模型](https://github.com/DeepRoboticsLab/deep_robotics_model)

## 7. 文件、依赖和测试

```text
xunyuan_eval/       记录、检查、评分和打包程序
references/         赛道规则和评分配置
examples/           使用样例
datasets/          数字和温度图片、答案、下载信息
docs/              接入方法、文件格式和评分规则
tests/             自动测试
```

### 需要安装什么

| 要做什么 | 需要什么 |
|---|---|
| 读取已有记录、算分、打包 | Python 3.10 或以上版本 |
| 从 MuJoCo 中记录机器人状态 | MuJoCo、NumPy，以及正在运行的仿真程序 |
| 识别数字和温度图片 | 图片和自己的 OCR 程序 |

### 评分器怎么知道机器人摔倒了

```text
机器人在仿真里运动 → 记录位置、姿态和碰撞 → 保存文件 → 评分器读文件算分
```

在 MuJoCo 仿真循环中调用 `MuJoCoSampler`，它从模拟器读取机器人状态，再交给 `TraceRecorder` 写进文件。其他仿真器按[运行记录格式](docs/protocol.md)保存同样的字段。

评分器逐条检查记录。当前规则中，机器人向左右或前后倾斜超过 **45°** 就算摔倒，还会检查碰撞、越界、动作是否合规、人工接管和超时。

独立通行测试发生安全问题时，那次不通过。连续任务发生问题时，保留此前已完成的成绩，后续项目计 0 分。记录缺字段或文件缺失时，程序会指出具体错误。

### 怎么检查程序能否正常工作

```bash
# 检查记录格式、评分、图片答案导出和打包功能
python3 -m unittest discover -s tests -v

# 检查 MuJoCo 的状态读取，需要安装 MuJoCo 和 NumPy
python3 -m unittest discover -s tests -p test_mujoco_adapter.py -v

# 用一个方块在重力下倾倒，检查姿态记录和摔倒判定
python3 -m examples.mujoco_fall_check --output artifacts/mujoco_fall_check
```

未安装 MuJoCo 时，相关测试显示 `skipped`，表示跳过。倾倒示例会保存两份运行记录和一个 `result.json`，可以查看直立和倾倒两种情况的结果。

想在每次推送代码时自动测试，可以把 `docs/ci-workflow.example.yml` 复制到 `.github/workflows/test.yml`。模板会用 Python 3.10、3.11、3.12、3.13 分别运行检查。
