# 项目运行接口

我们运行选手的代码，由选手代码加载自己的权重。项目持续运行，通过标准输入接收请求，通过标准输出回复结果，每行一个 JSON。日志写到标准错误，测评器会保存。

## 1. 启动和重置

程序启动后收到：

```json
{"op":"init","protocol":"xunyuan-project-v1","kind":"navigation","sensors":["front_rgb"],"request_id":1}
```

加载好模型后回复：

```json
{"request_id":1,"ready":true}
```

启动请求还带有 `sensor_config`，包含所选相机的内参、安装位置和方向，以及雷达的扫描参数。识别项目的 `kind` 是 `recognition`。每次回复带上对应请求的 `request_id`。

每条路线、每档扰动、每段视频开始前发送 `reset`。项目清空模型历史后回复 `ready=true`。启动最多 60 秒，重置最多 5 秒，每次推理最多 0.5 秒。

## 2. 导航输入

测评器每秒调用模型 50 次，发送：

```json
{"op":"predict","observation":"/tmp/xunyuan-project-example/observation.npz","request_id":3}
```

使用 `numpy.load(path, allow_pickle=False)` 读取该 NPZ。每次调用完成后才写下一份观测。

| 字段 | 大小和类型 | 内容 |
|---|---|---|
| `front_rgb` | `[144,256,3]`，uint8 | 前置 RGB 画面，0 至 255，选择视觉时提供 |
| `lidar_points` | `[N,3]`，float32 | 雷达坐标下 xyz，单位米，选择雷达时提供 |
| `instructions` | `[11]`，int64 | 去程五条、掉头一条、返程五条指令 |
| `imu` | `[6]`，float32 | 机身角速度 xyz、机身坐标下的单位重力方向 xyz |
| `joint_position` | `[16]`，float32 | 关节位置，弧度 |
| `joint_velocity` | `[16]`，float32 | 关节速度，弧度/秒 |
| `previous_action` | `[16]`，float32 | 上次输出的动作 |
| `time_s` | `[1]`，float64 | 当前控制时刻，秒 |
| `sensor_time_s` | `[1]`，float64 | 图像和雷达最近一次采样时刻，秒 |

方向编码：`1` 左转、`2` 直行、`3` 右转、`4` 掉头。模型从传感器观测发现路口，取出对应指令执行；离开这个路口后，再寻找下一个。

图像和雷达都每秒更新 10 次，两次采样之间保留上一份数据。具体参数见 `challenges/v3/model_interface.json`：前视垂直视场角 70°，位置在机身坐标下为 `(0.28,0,0.12)` 米；雷达为 16 线、水平 360°、每圈 128 个水平角，垂直 −15° 至 15°，范围 0.08 至 20 米。

雷达坐标方向为 x 向前、y 向左、z 向上，安装位置为机身坐标下 `(0.2,0,0.25)` 米，安装朝向与机身相同。只返回命中环境的有效点，`N` 可变，也可能为 0。点云由仿真射线与场景求交生成。

## 3. 导航输出

```json
{"request_id":3,"action":[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]}
```

16 个动作值都在 −1 至 1 之间。前 12 项按左前、右前、左后、右后排列，每条腿三个关节；后四项是这四个轮子。

腿目标为 `默认角度 + 动作 × 缩放值`，每条腿缩放 `0.25、0.6、0.8` 弧度；轮速为 `动作 × 35` 弧度/秒。默认角度和关节名在 `challenges/v3/robot/control.json`。

模型输出动作后，MuJoCo 每秒计算 200 步，测评器直接读取位置、姿态和接触状态。

## 4. 识别输入和输出

每帧发送：

```json
{"op":"predict","image":"/tmp/xunyuan-project-example/image.npy","video_id":"train01","time_s":12.4,"request_id":3}
```

NPY 中是 `[360,640,3]` 的 uint8 RGB 图像。程序按视频原始顺序逐帧调用，每秒 5 帧。项目可自行保存跨帧记忆，收到 `reset` 时清空。

回复示例：

```json
{
  "request_id":3,
  "detections":[
    {"box_xyxy":[0.4,0.3,0.6,0.5],"confidence":0.9,"status":"ok","value":"00127","unit":null},
    {"box_xyxy":[0.1,0.3,0.2,0.4],"confidence":0.8,"status":"ok","value":"38.2","unit":"C"}
  ]
}
```

坐标依次为左、上、右、下，除以图像宽高，范围 0 至 1。读数保存为文字，以保留前导零、负号和小数点。每帧最多 16 个标牌，空画面返回空列表。

看不清时，填写位置和可信度，使用 `status:"abstain"` 和 `reason:"display_unreadable"`。可信度低于 0.5 的输出跳过。视频编号和时刻由测评器记录。

## 5. 可运行示例

```bash
python -m tools.make_project_example --output artifacts/example_team
python -m xunyuan_eval check-submission --submission artifacts/example_team/submission.json --smoke
```

两个文件夹中的 `run.py` 展示了完整通信、权重加载和回复方法。替换其中的模型推理代码即可接入自己的实现。
