# 五张路线地图

`maps/` 中每张地图都有 MuJoCo 的 XML 文件和 PNG、SVG 预览图。机器人资源在 `robot/`。

`tasks/` 中每张地图有一份 JSON，按顺序给出去程、终点掉头和返程指令。`reference.json` 中保存评分用的参考轨迹、扣分阈值和扰动档位。

| 地图 | 去程指令 |
|---|---|
| [map01](maps/map01.png) | 左、直、右、左、右 |
| [map02](maps/map02.png) | 直、直、左、右、左 |
| [map03](maps/map03.png) | 右、左、直、右、直 |
| [map04](maps/map04.png) | 左、右、右、直、左 |
| [map05](maps/map05.png) | 直、左、右、左、直 |

路线每图 6 分，扰动每图 4 分，五图合计 50 分。具体算法见[扣分表](../../docs/rules.md)。

S10 机器人几何来自云深处 SDK，模型资源的 BSD 3-Clause 许可见 [robot/LICENSE-BSD-3-Clause.txt](robot/LICENSE-BSD-3-Clause.txt)。来源和文件校验值记录在 `robot/source.json`。
