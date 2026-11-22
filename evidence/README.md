# 评测证据
| 文件 | 说明 | 对应规约 |
|---|---|---|
| island_final/closure_report.json | 15 个片段的闭合检查：一次性片段首尾与中立姿势误差、循环片段首尾误差 | SPEC-DS-4/5 |
| island_final/build_log.txt | 片段构建日志：位置、路径长度、坐姿目标、衣摆、Cyclic 补全、裁剪区域 | SPEC-DS-3/8 |
| island_final/clips_*.json | 三个时段的片段清单（帧数、循环、起止位置、裁剪区域） | SPEC-DL-4 |
| island_final/render_log_night.txt | Mac 上的端到端试渲日志（25% 分辨率、8 采样） | — |
| island_final/compose_log_night.txt | 合成与 WebM 编码日志 | SPEC-DS-6 |
| island_final/compose_check.jpg | 合成检查四联图：遮罩 / 透明度 / 洋红底 / 叠到另一相位背景 | SPEC-DS-6 |
| island_final/windows_compose_report.md | Windows 正式渲染与合成检查报告：55 个视频齐全、0 错误、26 段抽帧检查 | SPEC-DS-3/6/7、SPEC-DL-4 |
| island_final/windows_file_inventory.csv | 全部成品视频的帧数、尺寸、编码、透明通道 | SPEC-DL-4 |
| island_final/island_topview.jpg | 岛屿俯视图（1 米网格），用于路径规划 | ADR-007 |
| island_final/scene_probe.json | 场景物体坐标探测结果 | — |
| motion/ | 15 个 Mixamo 动作重定向后的白模抽帧和日志 | ADR-005 |
| cloth/ | 斗篷物理 v1、v2 对比抽帧和日志 | SPEC-DS-8 |
| classroom/ | 魔法教室验收：循环误差、遮挡检查、规模统计、三时段预览 | ADR-002 |
| scene/ | 岛屿场景 v3、v4 预览图和日志 | SPEC-DS-2 |
| classroom_anim/build_log.txt、pack_log.txt | 教室人物片段构建、裁剪框与打包日志 | SPEC-DS-3/8 |
| classroom_anim/clips_classroom_final.json | 教室成品片段清单（含 layer：elaina / teacher） | SPEC-DL-4 |
| classroom_anim/render_log_classroom.txt、compose_log_classroom.txt | Windows 正式渲染（55 分钟）与合成（12 分钟）日志，0 错误 | SPEC-DS-6 |
| classroom_anim/成品检查报告.md、video_validation.json | Windows 成品检查：帧数、透明通道、预览逐段抽帧 | SPEC-DS-7、SPEC-DL-4 |
| classroom_anim/mask_before_after.jpg | 遮罩修复前后：光尘打出的黑孔（左）→ 排除光尘后（右） | SPEC-DS-6 |
| classroom_anim/final_T*_together_sheet.jpg、eevee_*.jpg、compose_check.jpg | 师生同框成品抽帧、EEVEE 静帧、合成检查 | SPEC-DS-7 |
| classroom_anim/staff2_sheet.jpg | 教鞭朝向修复后的白模抽帧（走路斜向前下，不穿模） | SPEC-DS-7 |
