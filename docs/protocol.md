# 运行记录和成绩文件

选手提交模型后，测评程序生成以下文件。

## 1. run.json

它列出每次运行的地图、扰动档位、结束原因和详细记录位置：

```json
{
  "schema_version": "2.0",
  "reference_id": "xunyuan-v2-five-routes-20261125",
  "team": "队伍名称",
  "routes": [
    {"route_id": "map01", "termination": "completed", "trace": "map01/normal/physics.jsonl"}
  ],
  "disturbance": [
    {"route_id": "map01", "force_N": 0.5, "termination": "completed", "trace": "map01/force_0.5/physics.jsonl", "force_record": "map01/force_0.5/forces.json"}
  ],
  "video_predictions": "video_predictions.json"
}
```

结束原因有 `completed` 正常完成、`timeout` 超时、`crashed` 模型运行出错、`safety_stop` 安全停止。运行清单还保存模型校验值和随机种子。

## 2. physics.jsonl

每 0.005 秒一条记录。第一条时间为 0，之后时间依次增加。位置、姿态和接触由 MuJoCo 读取。

| 字段 | 内容 |
|---|---|
| `time_s` | 仿真时间，秒 |
| `position_m` | 主体位置 xyz，米 |
| `yaw_rad` | 朝向，弧度 |
| `roll_rad` / `pitch_rad` | 左右、前后倾斜，弧度 |
| `speed_mps` | 实际水平速度，米/秒 |
| `yaw_rate_rps` | 转向速度，弧度/秒 |
| `envelope_points_m` | 包围机器人碰撞部件的一组角点 |
| `forbidden_contacts` | 当前步发生的禁止接触次数 |
| `out_of_bounds` | 是否越界 |
| `action_valid` | 动作是否符合接口要求 |
| `intervention` | 是否发生人工接管或位置重设 |
| `force_world_N` | 当前步施加的外力 xyz，牛 |

开关字段填写 `true` 或 `false`。每次运行使用单独的文件。

## 3. states.json

这是每秒摘要，方便看机器人走到了哪里：

```json
{
  "states": [
    {"time_s": 1.0, "status": 0, "relative_position_m": [0.2, 0.0, 0.0], "roll_rad": 0.02, "pitch_rad": 0.01, "collision": false}
  ],
  "termination": "timeout",
  "reason": "timeout"
}
```

`status`：`0` 运行中，`1` 完成，`-1` 失败。发生碰撞时会及时追加失败状态。

`relative_position_m` 是相对本次起始位置的 xyz 位移，方向采用地图坐标轴。

## 4. video_predictions.json

每条结果包含视频编号、时间、标牌位置和识别结果。例如：

```json
{
  "detections": [
    {"video_id": "test01", "time_s": 25.0, "box_xyxy": [0.4, 0.4, 0.6, 0.6], "confidence": 0.9, "status": "ok", "value": "00127", "unit": null},
    {"video_id": "test01", "time_s": 75.0, "box_xyxy": [0.3, 0.4, 0.5, 0.6], "confidence": 0.8, "status": "abstain", "reason": "display_unreadable"}
  ]
}
```

数字按文字保存。温度单位为 `C`，普通数字单位为 `null`。坐标除以图像宽高，变成 0 至 1。

## 5. report.json

主要字段：

| 字段 | 内容 |
|---|---|
| `navigation_control_score` | 导航和运控合计，满分 50 |
| `scores.route` | 路线分，满分 30 |
| `scores.disturbance` | 扰动分，满分 20 |
| `scores.recognition` | 视频识别分，满分 20 |
| `automated_score` | 三项自动分合计，满分 70 |
| `pending_manual` | 等待评委填写的报告分，满分 30 |
| `details` | 每张地图、每档扰动的分数和原因 |

使用 `add-report-score` 后，结果会增加 `scores.report` 和 `final_score`，得到 100 分制总成绩。
