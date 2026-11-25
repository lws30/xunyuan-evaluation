# 运行记录怎么写

评分器读取两样东西：`run.json` 告诉它有哪些测试，JSONL 文件告诉它每次测试里机器人怎么运动。

## 1. 文件放在哪里

```text
my_run/
  run.json
  traces/
    M01_T1.jsonl
    M01_T2.jsonl
    ...
    R1.jsonl
    R2.jsonl
    R3.jsonl
```

一次测试保存一份记录，路径写成 `traces/R1.jsonl` 这样的相对路径，以 `run.json` 所在目录为起点。

## 2. run.json 写什么

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

| 字段 | 填什么 |
|---|---|
| `schema_version` | 运行记录格式版本，当前为 `1.0` |
| `reference_id` | 本次使用的规则文件中的同名值 |
| `team` / `method` | 队伍名称和算法版本名称 |
| `policy_sha256` | 算法文件的 SHA-256 校验值，共 64 个小写十六进制字符 |
| `locomotion` | 各次通行测试的记录列表 |
| `rounds` | 各轮连续任务的记录列表 |
| 每项的 `id` | 规则文件中对应测试或轮次的 ID |
| 每项的 `trace` | 这次运行记录的文件路径 |
| 每项的 `termination` | 这次运行如何结束 |

示例里的校验值用于展示格式。实际使用时，给加载的算法文件计算 SHA-256，并填入清单；有多个文件时，可以把按固定顺序排列的文件校验值再合并计算一次。同一算法版本的各次测试使用相同的 `policy_sha256`。

`termination` 有四种写法：

| 值 | 含义 |
|---|---|
| `completed` | 正常结束 |
| `timeout` | 超时 |
| `crashed` | 异常结束 |
| `safety_stop` | 因安全问题停止 |

测试或轮次少了一项，那项按 0 分计算。测试 ID、算法校验值和规则版本要与本次运行对应，每次测试使用自己的记录文件。

## 3. 每一步记录什么

JSONL 文件每行保存一个 JSON 对象。第一条的时间是 0，之后时间依次增加。例如：

```json
{"time_s":0,"position_m":[0,0,0.5],"yaw_rad":0,"roll_rad":0,"pitch_rad":0,"speed_mps":0,"yaw_rate_rps":0,"envelope_points_m":[[-0.2,-0.1,0.2],[-0.2,0.1,0.2],[0.2,-0.1,0.2],[0.2,0.1,0.2]],"forbidden_contacts":0,"out_of_bounds":false,"action_valid":true,"intervention":false}
```

| 字段 | 含义 |
|---|---|
| `time_s` | 从本次测试开始算起的仿真时间，单位秒 |
| `position_m` | 机器人主体在地图中的 xyz 位置，单位米 |
| `yaw_rad` | 朝向角，单位弧度 |
| `roll_rad` / `pitch_rad` | 左右倾斜角、前后倾斜角，单位弧度 |
| `speed_mps` | 实际水平速度，单位米/秒 |
| `yaw_rate_rps` | 实际转向速度，单位弧度/秒 |
| `envelope_points_m` | 围住整台机器人碰撞部件的一组角点，使用地图坐标，至少四个，整段记录点数保持一致 |
| `forbidden_contacts` | 当前物理步不符合接触规则的碰撞数量 |
| `out_of_bounds` | 是否越界，填 `true` 或 `false` |
| `action_valid` | 当前动作是否符合控制接口要求，填 `true` 或 `false` |
| `intervention` | 是否发生人工扶持、接管或位置重设，填 `true` 或 `false` |

这些字段都要填写。数值字段使用有限数字，开关字段使用 `true` 或 `false`。机器人位置、出口和停靠点使用同一套地图坐标。

## 4. 谁来保存这些数据

在仿真程序里，从模拟器读取位置、姿态、速度和接触情况；按场景检查越界，按控制接口检查动作，然后写入文件。比赛运行时由评测程序负责保存。

具体代码见[仿真接入方法](integration.md)。

## 5. 程序出错时怎么看

命令正常完成时返回 0。文件缺失、JSON 写错、时间顺序错误或版本不匹配时返回 2，并打印具体原因。机器人测试失败时仍然会生成成绩，原因写在 `report.json` 中。
