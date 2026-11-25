# 将自己的运行接入自评

## 推荐接入点

在模拟器或评测调度进程中接入 `TraceRecorder`，每个物理步记录状态。在线策略保持原有传感器输入；全局真值和裁判字段由模拟器侧构造。

```python
from xunyuan_eval.recorder import TraceRecorder

# 启动新试次、完成状态初始化后，先记录 time_s=0 的帧。
with TraceRecorder("my_run/traces/M01_T1.jsonl") as recorder:
    recorder.append(evaluator_snapshot())
    while trial_is_running():
        observation = make_allowed_observation()
        action = agent.step(observation)
        validate_and_apply_action(action)
        advance_one_physics_step()
        recorder.append(evaluator_snapshot())
```

以上名称中的 `evaluator_snapshot()`、状态循环和动作桥接由你的运行环境实现。快照的完整字段见 [协议](protocol.md)。发生崩溃或超时也应关闭记录器、保留已写入轨迹并在清单中记录实际终止原因。新试次使用新文件，不能覆盖前一轮。

## MuJoCo 适配器

仓库提供 `xunyuan_eval.mujoco_recorder.MuJoCoSampler`，不依赖特定策略。调用方按场景显式提供：

- S10 根刚体名称。
- 属于允许地形的 geom 名称。
- 可以接触地形的连杆名称。轮胎以外的膝/胫等部位是否允许，由冻结规则决定。
- 完整外廓的区域边界检查器；返回 `True` 表示越界。

```python
from xunyuan_eval.mujoco_recorder import MuJoCoSampler
from xunyuan_eval.recorder import TraceRecorder

sampler = MuJoCoSampler(
    model,
    root_body="base_link",
    terrain_geom_names=scene_terrain_names,
    allowed_terrain_body_names=frozen_allowed_contact_bodies,
    boundary_check=scene_boundary_checker,
)

with TraceRecorder("my_run/traces/R1.jsonl") as recorder:
    # data 的运动学与接触应已更新；初始帧 time_s=0。
    recorder.append(sampler.sample(data, action_valid=True))
    while running:
        # 在评测侧校验原始动作；越界/非法动作不能先裁剪再标为合法。
        legal = action_validator(raw_action)
        step_simulation(raw_action)
        # 必要时调用 mj_forward 保证当前时间的姿态和接触同步。
        recorder.append(sampler.sample(data, action_valid=legal))
```

`MuJoCoSampler` 使用根刚体子树中的所有碰撞 geom，为各 geom 的局部 AABB 变换八个角点，形成保守整机外廓；使用实际刚体速度和接触记录，不读取策略给出的“已完成”标志。接触分类中，机器人与明确允许地形/连杆的接触可接受，其他涉及机器人的接触按禁止接触记录，包括未允许的自碰撞。

适配器不会推断赛道允许区域，也不会猜测轮子名称。必须实现真正的场景边界检查，不能用恒为 `False` 的占位函数提交正式记录。穿越过程中若碰撞只持续一个物理步，也需要记录；不得仅按视频帧率采样。

## V3 场景与参考配置

`references/public_dev_v3_candidate.json` 是为选手公开的开发判据：

- `M01_T1..3`、`M02_T1..3`、`M03_T1..3`、`M04_T1..3`、`M05_T1..3`、`M06_T1..3`、`M08_T1..3`。
- M02 第二次使用右转场景，其余两次左转。
- 三轮 `R1..R3` 每轮 N01..N05、D01..D04；A 点去程与返程分别算 D01、D03。
- 每个参考出口门含世界系中心、水平单位法线和宽度；导航只接受沿法线正向的穿越。

该文件只发布公开开发几何的判据与建议阈值。完整场景资源与初态由赛事方的场景包提供，文件中不含正式隐藏地图、未来扰动表或识别答案。若采用不同的公开场景，需由赛事方发布新的 `reference_id` 与对应判据，不能只改自己的输出版本号。

## 尚未提供的运行平台

当前工具覆盖离线自评分、MuJoCo 状态采样和自评记录打包。算法容器调度、传感器白名单桥接、完整地图资源分发、官方连续录像与在线排行榜需要运行平台另外提供。本仓库的协议样例不代表这些环节已经完成联调。
