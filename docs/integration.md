# 把仿真结果交给评分器

整个过程分三步：**运行机器人、保存状态、读取文件算分**。

## 1. 在哪里加记录代码

把记录器加在仿真程序每次推进物理计算的位置。每推进一步，就记一次位置、姿态、速度和碰撞情况。

```text
模拟器 → 相机、雷达等观测 → 算法决定动作 → 模拟器执行动作
   └→ 位置、姿态、速度、碰撞 → 记录文件 → 评分器
```

算法用传感器观测决定怎么走。评分器用模拟器记录的状态判断走得怎么样。比赛运行时，由评测程序负责保存这些状态。

每次测试从时间 0 开始记录，单独保存一个 JSONL 文件。JSONL 就是一行一条状态记录。所有字段见[运行记录格式](protocol.md)。测试结束、超时或程序出错后，都保存已经写下的内容，并在 `run.json` 中填写结束原因。

## 2. MuJoCo 怎么接

仓库里有两个现成工具：

- `MuJoCoSampler`：从 MuJoCo 里取出这一时刻的机器人状态。
- `TraceRecorder`：把取出的状态逐行写进文件。

接入前，先确认四件事：

| 配置 | 填什么 |
|---|---|
| `root_body` | 机器人主体的名称，例如 `base_link` |
| `terrain_geom_names` | 地面、坡道、台阶等允许行驶表面的名称 |
| `allowed_terrain_body_names` | 允许碰到地面的机器人部位名称，例如轮子 |
| `boundary_check` | 检查机器人是否越界的函数；越界返回 `True` |

下面的片段放进现有仿真循环。`model`、`data`、算法动作和场景检查函数由你的仿真程序提供。

```python
import mujoco
from xunyuan_eval.mujoco_recorder import MuJoCoSampler
from xunyuan_eval.recorder import TraceRecorder

sampler = MuJoCoSampler(
    model,
    root_body="base_link",
    terrain_geom_names=scene_terrain_names,
    allowed_terrain_body_names=allowed_contact_bodies,
    boundary_check=scene_boundary_checker,
)

mujoco.mj_forward(model, data)
with TraceRecorder("my_run/traces/R1.jsonl") as recorder:
    recorder.append(sampler.sample(data, action_valid=True))
    while running:
        # 取出算法动作，按控制接口的要求检查动作
        raw_action = get_policy_action()
        legal = action_validator(raw_action)
        apply_action(raw_action)

        # 推进一步，更新姿态和碰撞，再保存这一时刻的状态
        mujoco.mj_step(model, data)
        mujoco.mj_forward(model, data)
        recorder.append(sampler.sample(data, action_valid=legal))
```

如果算法每隔几个物理步才更新一次动作，记录器仍然要在每个物理步调用。V3 配置的记录间隔是 0.005 秒。

采样器会读取机器人所有碰撞部件的包围盒，用这些盒子的角点判断整台机器人是否通过出口、是否越界。它也会读取当前的接触：允许的部位碰到允许的地形算正常接触，其余涉及机器人的接触会记入 `forbidden_contacts`。

## 3. 怎么判断摔倒

记录中的 `roll_rad` 表示左右倾斜，`pitch_rad` 表示前后倾斜，单位是弧度。

当前规则中，任意一项的绝对值超过 45°，就触发摔倒判定，原因记为 `fall`。碰撞、越界等问题也会触发失败，报告会列出评分时先遇到的原因。

可以先跑一个现成例子，看看记录和结果长什么样：

```bash
python3 -m examples.mujoco_fall_check --output artifacts/mujoco_fall_check
```

这个例子使用一个能绕轴转动的方块。直立时它保持不动，略微倾斜时会在重力下倒下。程序会保存 `upright.jsonl`、`tipping.jsonl` 和 `result.json`。倾倒记录经过评分函数检查后，结果中的原因应为 `fall`。

## 4. 其他仿真器怎么接

在 Isaac Sim、ROS 或自己的模拟器中，按[运行记录格式](protocol.md)整理相同的字段，再用 `TraceRecorder` 保存。位置、姿态、速度和接触从对应的模拟器接口取得；越界和动作检查按场景与控制接口实现。

## 5. 配好规则，开始算分

规则文件中的出口和停靠点要与当前赛道一致。仓库附带的 `references/public_dev_v3_candidate.json` 对应 V3 约 50 米开发路线：

- 21 次独立通行测试，每类场景跑 3 次。
- 连续任务共跑 3 轮，每轮有 5 次路口选择和 4 次停靠。
- A 点去程和返程分别计一次停靠。

运行结束后，把记录文件列入 `run.json`，再执行：

```bash
python3 -m xunyuan_eval evaluate \
  --run my_run/run.json \
  --reference references/public_dev_v3_candidate.json \
  --output artifacts/my_report.json
```

打开 `artifacts/my_report.json`，查看各项得分和原因。
