# 五张 S10 地图

每张图五个 T/Y 路口，完成去程后按返程指令回到起点。地图图片、物理环境和参考轨迹使用同一份几何数据。

| 地图 | 去程指令 | 图片 | 任务 |
|---|---|---|---|
| 1 | 左、直、右、左、右 | [地图1](maps/map01.png) | [任务1](tasks/map01.json) |
| 2 | 直、直、左、右、左 | [地图2](maps/map02.png) | [任务2](tasks/map02.json) |
| 3 | 右、左、直、右、直 | [地图3](maps/map03.png) | [任务3](tasks/map03.json) |
| 4 | 左、右、右、直、左 | [地图4](maps/map04.png) | [任务4](tasks/map04.json) |
| 5 | 直、左、右、左、直 | [地图5](maps/map05.png) | [任务5](tasks/map05.json) |

`reference.json` 保存路线、从高到低的推力档位和四档地面摩擦。`calibration.json` 保存训练模型的扰动实测数据。`model_interface.json` 保存相机和雷达参数。

机器人网格和原始模型来自云深处 [SDK](https://github.com/DeepRoboticsLab/sdk_deploy)，许可文件与来源记录在 `robot/` 中。
