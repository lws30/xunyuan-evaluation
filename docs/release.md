# 发布与复核说明

## 公开内容

本仓库公开评分实现、通用遥测记录器、MuJoCo 采样适配器、公开开发几何参考、合成协议/读数样例、测试和文档。没有附带个人运控算法、训练权重、实验录像、历史运行轨迹、账号信息或机器专用文件。

V3 开发参考只保留独立测试出口、公开练习路线的判定门与停靠参数。没有复制旧工程整包，也没有将旧 `rules.json` 中的其他评分权重直接沿用。

## 版本与正式评测

发布版本为 0.1.0，遥测协议为 1.0。参考配置有独立 `reference_id` 与状态字段。任何影响分母、判据、阈值和场景坐标的调整都应更新参考标识，并以发布说明通知选手。

正式裁判可复用同一评分函数，但必须使用赛事方采集的轨迹和正式参考文件。正式隐藏参考配置不放在本公开仓库。自评记录包不能替代算法镜像，也不能直接作为官方成绩来源。

## 参考项目

- [DriveLM challenge](https://github.com/OpenDriveLab/DriveLM/tree/main/challenge)：参考“样例数据、离线评测、提交准备、正式测试入口”分离的公开结构。
- [AGC2024 driving-with-language-official](https://huggingface.co/spaces/AGC2024/driving-with-language-official)：参考选手提交与状态展示的组织方式。

这里只参考工作流组织，未移植其语言评测算法、模型或数据。

## 自动测试工作流

本次 GitHub 授权缺少 `workflow` 权限，GitHub 拒绝了包含 `.github/workflows/` 文件的首次推送。发布版将其保留为 `docs/ci-workflow.example.yml` 模板，未启用托管 CI；本地 32 项测试已在包含 MuJoCo 的环境全部通过。
