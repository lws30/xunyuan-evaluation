# 自评文件协议 1.0

## 运行目录

```text
my_run/
  run.json
  traces/
    M01_T1.jsonl
    ...
    M08_T3.jsonl
    R1.jsonl
    R2.jsonl
    R3.jsonl
```

`run.json` 示例：

```json
{
  "schema_version": "1.0",
  "reference_id": "xunyuan-public-v3-candidate-20261125",
  "team": "Team01",
  "method": "method-version-1",
  "policy_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "locomotion": [
    {
      "id": "M01_T1",
      "termination": "completed",
      "trace": "traces/M01_T1.jsonl",
      "policy_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    }
  ],
  "rounds": []
}
```

示例中的哈希是格式占位符。实际使用时由评测进程计算加载策略文件的 SHA-256；若一个策略含多个文件，可对固定顺序的模型、代码和配置校验清单再计算一个组合哈希。同一参评版本各试次的策略标识必须一致。

允许缺少整个试次或轮次，缺少的项按 0 分保留分母。重复 ID、未知 ID、一个文件复用为两个试次、不同策略标识、版本不一致属于格式错误。`termination` 只接受 `completed`、`timeout`、`crashed`、`safety_stop`；`completed` 不会直接产生得分。

轨迹路径相对于 `run.json` 所在目录。绝对路径、`..`、逃逸目录的符号链接和重复 JSON 键会被拒绝。

## 逐帧遥测

JSONL 每行是一个完整对象。以下仅展示一帧；有效连续轨迹必须从 `time_s=0` 开始，时间严格增加。

```json
{"time_s":0,"position_m":[0,0,0.5],"yaw_rad":0,"roll_rad":0,"pitch_rad":0,"speed_mps":0,"yaw_rate_rps":0,"envelope_points_m":[[-0.2,-0.1,0.2],[-0.2,0.1,0.2],[0.2,-0.1,0.2],[0.2,0.1,0.2]],"forbidden_contacts":0,"out_of_bounds":false,"action_valid":true,"intervention":false}
```

| 字段 | 含义与来源 |
|---|---|
| `time_s` | 本试次仿真时间，秒；由模拟器记录 |
| `position_m` | 世界坐标系中的机身参考点 xyz，米；与参考配置同坐标系 |
| `yaw_rad` / `roll_rad` / `pitch_rad` | 机身朝向，弧度 |
| `speed_mps` | 实际水平速度模长，不是速度指令 |
| `yaw_rate_rps` | 实际绕世界竖直轴的角速度，弧度/秒 |
| `envelope_points_m` | 包围整机规定碰撞外廓的世界系支撑点，点数全程固定，至少四个；不能只提供轮子或机身中心 |
| `forbidden_contacts` | 这一物理步禁止接触的数量；由裁判接触分类器计算 |
| `out_of_bounds` | 整机外廓是否违反允许区域；由场景边界检查器计算 |
| `action_valid` | 动作是否有限、顺序正确且在冻结接口范围内；由控制接口检查 |
| `intervention` | 是否发生扶持、人工接管或未允许的位置重设；由评测进程记录 |

所有数值必须有限，数值字段不接受布尔值。缺字段不能用“默认安全”补齐。角度使用弧度，距离使用米，时间使用秒。JSON 中的 `NaN`、`Infinity` 会被拒绝。

`envelope_points_m` 以外接包围体近似真实碰撞几何时，越线判定较保守；这是可接受的自评近似。正式冻结时须规定统一外廓定义，不能各队任意选择点数与形状。

## 裁判与算法的信息边界

这些全局位置、碰撞、外廓和正确出口属于**评测进程记录**，并不是选手在线算法的输入接口。算法仅接收比赛公开的传感器与任务。不要为接入自评工具向算法开放完整 MuJoCo `model/data`。

本地用户能修改自评轨迹，因此自评工具不能认证日志真实性。正式评测须由赛事方直接运行算法并独立采集遥测，以同一评分实现重算。各文件哈希用于标识和复核文件，不构成真实性签名。
