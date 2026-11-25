# 运行记录和成绩文件

运行代码、权重和 AGENT.md 来自选手。仿真记录和成绩文件由测评程序生成。

## 1. run.json

记录队伍、规则版本、随机种子、传感器配置和各次运行：

```json
{
  "schema_version":"3.0",
  "reference_id":"xunyuan-v3-five-routes-20261126",
  "team":"队伍名称",
  "sensors":["front_rgb","lidar_points"],
  "routes":[{"route_id":"map01","termination":"completed","trace":"map01/normal/physics.jsonl"}],
  "disturbance":[{"route_id":"map01","force_N":60,"termination":"completed","trace":"map01/force_60/physics.jsonl","force_record":"map01/force_60/forces.json"}],
  "friction":[{"route_id":"map01","friction":0.1,"termination":"completed","trace":"map01/friction_0.1/physics.jsonl"}]
}
```

清单还包含 `submission_sha256` 和 `input_sha256`，分别记录项目文件和测评输入的校验值。`video_split` 表示使用训练还是测试视频。模型启动等错误记录在 `model_errors`。

## 2. physics.jsonl

每 0.005 秒一条记录，位置、姿态和接触来自 MuJoCo。

| 字段 | 内容 |
|---|---|
| `time_s` | 仿真时间，秒 |
| `position_m` | 主体 xyz 位置，米 |
| `yaw_rad` | 朝向，弧度 |
| `roll_rad` / `pitch_rad` | 左右、前后倾斜，弧度 |
| `speed_mps` | 实际水平速度，米/秒 |
| `yaw_rate_rps` | 转向速度，弧度/秒 |
| `envelope_points_m` | 机器人碰撞部件的包围点 |
| `forbidden_contacts` | 当前步禁止接触次数 |
| `out_of_bounds` | 是否越界 |
| `action_valid` | 动作是否有效 |
| `intervention` | 是否人工接管或重设位置 |
| `force_world_N` | 当前步施加的外力 xyz，牛 |
| `ground_contact_friction` | 当前有效地面接触实际使用的滑动摩擦系数；离地时为空列表 |

每次运行单独保存文件。评分器按这些详细记录检查轨迹、碰撞、推力和摩擦。

## 3. states.json

每秒保存时间、相对起点的 xyz 位移、横滚、俯仰和碰撞状态。结束时追加最终状态，并记录原因。

`status`：`0` 运行中，`1` 完成，`-1` 失败。相对位移采用地图坐标轴方向。

## 4. forces.json

每个推力档位记录力大小、三次施力的开始时间、实际持续时间和世界坐标下的外力向量。评分器将记录与每个物理步的外力核对。

## 5. video_predictions.json

每条标牌结果包含视频编号、时间、位置、可信度、是否看清和读数。视频编号与时间由测评器补入，其余字段由选手识别代码输出，格式见[运行接口](model-interface.md)。

## 6. report.json

| 字段 | 内容 |
|---|---|
| `scores.route.score` | 路线分，满分 30 |
| `scores.disturbance.push.score` | 推力分，满分 10 |
| `scores.disturbance.friction.score` | 低摩擦分，满分 10 |
| `scores.recognition.score` | 识别分，满分 20 |
| `navigation_control_score` | 导航和运控合计，满分 50 |
| `automated_score` | 自动分合计，满分 70 |
| `pending_manual` | 待填写的报告分，满分 30 |
| `details.routes` | 每张地图的路线得分和偏离 |
| `details.disturbance` | 从高到低各档推力的得分和原因 |
| `details.friction` | 从最滑到正常各档地面的得分和原因 |
| `sensors` | 视觉、雷达或融合配置 |

训练识别反馈包含正确答案，正式识别成绩只列模型输出和对错。使用 `add-report-score` 后增加 `scores.report` 和 `final_score`，得到 100 分制总成绩。
