# 评测证据
| 文件 | 说明 | 对应规约 |
|---|---|---|
| island_final/closure_report.json | 15 个片段的闭合检查：一次性片段首尾与中立姿势误差、循环片段首尾误差 | SPEC-DS-4/5 |
| island_final/build_log.txt | 片段构建日志：位置、路径长度、坐姿目标、衣摆、Cyclic 补全、裁剪区域 | SPEC-DS-3/8 |
| island_final/clips_*.json | 三个时段的片段清单（帧数、循环、起止位置、裁剪区域） | SPEC-DL-4 |
| island_final/render_log_night.txt | Mac 上的端到端试渲日志（25% 分辨率、8 采样） | — |
| island_final/compose_log_night.txt | 合成与 WebM 编码日志 | SPEC-DS-6 |
| island_final/compose_check.jpg | 合成检查四联图：遮罩 / 透明度 / 洋红底 / 叠到另一相位背景 | SPEC-DS-6 |
| island_final/island_topview.jpg | 岛屿俯视图（1 米网格），用于路径规划 | ADR-007 |
| island_final/scene_probe.json | 场景物体坐标探测结果 | — |
| motion/ | 15 个 Mixamo 动作重定向后的白模抽帧和日志 | ADR-005 |
| cloth/ | 斗篷物理 v1、v2 对比抽帧和日志 | SPEC-DS-8 |
| classroom/ | 魔法教室验收：循环误差、遮挡检查、规模统计、三时段预览 | ADR-002 |
| scene/ | 岛屿场景 v3、v4 预览图和日志 | SPEC-DS-2 |
