# 修复后合成与产物检查报告

检查时间：2026-11-16T09:34:04（北京时间）。

实际运行原始 5_compose_only.bat，开始 2026-11-16T08:48:36.6505679+08:00，结束 2026-11-16T09:13:52.0544960+08:00。仅复用已有原始帧进行合成与视频编码。

替换后 compose_island.py SHA256：4E9C22CD75FB939A5F9C457FF2D57609DE1E6AEB5C18496A48F3BF90CA52FF1A。原脚本与旧日志已保存在本检查目录 before_* 子目录。

## 参数与完整性

- 视频文件 55/55，目录文件 58/58（包括 3 份 clips JSON）。
- 预览完整解码 26/26 段，共 3079 帧。
- layer PNG 数量 3079/3079。
- 原始 PNG 6734 张，文件长度/修改时间变化 0 项；未触发原始帧渲染。
- 原始 blend、render_island.py 和 5_compose_only.bat 哈希变化 0 项。
- 参数核验错误 0 项。详见 summary.json 与 review/verification_*.json。

| 时段 | 片段清单 | 合成日志末行 | 合成出错 | 视频编码出错 |
|---|---:|---|---:|---:|
| night | 9/9 | 08:59:52 [night] 合成完成，用时 11.2 分钟 | 0 | 0 |
| morning | 8/8 | 09:08:11 [morning] 合成完成，用时 8.2 分钟 | 0 | 0 |
| noon | 9/9 | 09:13:50 [noon] 合成完成，用时 5.6 分钟 | 0 | 0 |

三个背景视频要求 192 帧、2560×1440；WebM 的帧数和宽高逐项对照 output/video/clips_*.json，并检查 VP9 与 alpha_mode=1。预览要求 1280×720，帧数与清单一致。完整机器核验结果在 review/verification_*.json。

## 全部文件清单

| 文件名 | 大小（字节） | 帧数 | 尺寸 | 编码 | alpha_mode |
|---|---:|---:|---|---|---|
| A1_idle_morning.webm | 6034817 | 192 | 1060×630 | vp9 | 1 |
| A1_idle_night.webm | 9299309 | 192 | 896×630 | vp9 | 1 |
| A1_idle_noon.webm | 2529268 | 192 | 724×324 | vp9 | 1 |
| A3_stretch_morning.webm | 7498527 | 214 | 1068×674 | vp9 | 1 |
| B2_wave_morning.webm | 3756713 | 77 | 1084×666 | vp9 | 1 |
| B2_wave_night.webm | 5162955 | 77 | 918×666 | vp9 | 1 |
| B2_wave_noon.webm | 1388407 | 77 | 740×334 | vp9 | 1 |
| B3_cheer_morning.webm | 4062026 | 79 | 1088×686 | vp9 | 1 |
| B3_cheer_night.webm | 5582009 | 79 | 944×686 | vp9 | 1 |
| B3_cheer_noon.webm | 1551429 | 79 | 754×346 | vp9 | 1 |
| B4_rush_night.webm | 39106761 | 160 | 1692×1094 | vp9 | 1 |
| bg_morning.mp4 | 7358967 | 192 | 2560×1440 | h264 | — |
| bg_night.mp4 | 8286735 | 192 | 2560×1440 | h264 | — |
| bg_noon.mp4 | 8769482 | 192 | 2560×1440 | h264 | — |
| C1a_yawn_morning.webm | 9544356 | 201 | 1070×688 | vp9 | 1 |
| C1b_water_morning.webm | 5331591 | 135 | 1038×658 | vp9 | 1 |
| C2b_feed_noon.webm | 2850858 | 135 | 726×404 | vp9 | 1 |
| C3_fire_in_night.webm | 3900129 | 55 | 932×678 | vp9 | 1 |
| C3_fire_in_noon.webm | 1310343 | 55 | 778×344 | vp9 | 1 |
| C3_fire_loop_night.webm | 10004516 | 192 | 872×644 | vp9 | 1 |
| C3_fire_loop_noon.webm | 2551409 | 192 | 672×308 | vp9 | 1 |
| C3_fire_out_night.webm | 4034973 | 55 | 916×710 | vp9 | 1 |
| C3_fire_out_noon.webm | 1297516 | 55 | 762×352 | vp9 | 1 |
| clips_morning.json | 2955 | — | — | — | — |
| clips_night.json | 3184 | — | — | — | — |
| clips_noon.json | 3168 | — | — | — | — |
| preview_A1_idle_morning.mp4 | 2962246 | 192 | 1280×720 | h264 | — |
| preview_A1_idle_night.mp4 | 3429633 | 192 | 1280×720 | h264 | — |
| preview_A1_idle_noon.mp4 | 3492924 | 192 | 1280×720 | h264 | — |
| preview_A3_stretch_morning.mp4 | 3295238 | 214 | 1280×720 | h264 | — |
| preview_B2_wave_morning.mp4 | 1275825 | 77 | 1280×720 | h264 | — |
| preview_B2_wave_night.mp4 | 1474618 | 77 | 1280×720 | h264 | — |
| preview_B2_wave_noon.mp4 | 1514578 | 77 | 1280×720 | h264 | — |
| preview_B3_cheer_morning.mp4 | 1302271 | 79 | 1280×720 | h264 | — |
| preview_B3_cheer_night.mp4 | 1506637 | 79 | 1280×720 | h264 | — |
| preview_B3_cheer_noon.mp4 | 1545790 | 79 | 1280×720 | h264 | — |
| preview_B4_rush_night.mp4 | 2884232 | 160 | 1280×720 | h264 | — |
| preview_C1a_yawn_morning.mp4 | 3221468 | 201 | 1280×720 | h264 | — |
| preview_C1b_water_morning.mp4 | 2152990 | 135 | 1280×720 | h264 | — |
| preview_C2b_feed_noon.mp4 | 2547598 | 135 | 1280×720 | h264 | — |
| preview_C3_fire_in_night.mp4 | 1053048 | 55 | 1280×720 | h264 | — |
| preview_C3_fire_in_noon.mp4 | 1088337 | 55 | 1280×720 | h264 | — |
| preview_C3_fire_loop_night.mp4 | 3431143 | 192 | 1280×720 | h264 | — |
| preview_C3_fire_loop_noon.mp4 | 3486744 | 192 | 1280×720 | h264 | — |
| preview_C3_fire_out_night.mp4 | 1051960 | 55 | 1280×720 | h264 | — |
| preview_C3_fire_out_noon.mp4 | 1081802 | 55 | 1280×720 | h264 | — |
| preview_W_fire_stand_night.mp4 | 2109545 | 111 | 1280×720 | h264 | — |
| preview_W_fire_stand_noon.mp4 | 2164944 | 111 | 1280×720 | h264 | — |
| preview_W_planter_stand_morning.mp4 | 1076906 | 71 | 1280×720 | h264 | — |
| preview_W_stand_fire_night.mp4 | 2116260 | 111 | 1280×720 | h264 | — |
| preview_W_stand_fire_noon.mp4 | 2177451 | 111 | 1280×720 | h264 | — |
| preview_W_stand_planter_morning.mp4 | 1079431 | 71 | 1280×720 | h264 | — |
| W_fire_stand_night.webm | 17067725 | 111 | 1358×882 | vp9 | 1 |
| W_fire_stand_noon.webm | 5541068 | 111 | 1164×548 | vp9 | 1 |
| W_planter_stand_morning.webm | 4590398 | 71 | 1392×736 | vp9 | 1 |
| W_stand_fire_night.webm | 16946123 | 111 | 1342×878 | vp9 | 1 |
| W_stand_fire_noon.webm | 5745985 | 111 | 1170×556 | vp9 | 1 |
| W_stand_planter_morning.webm | 4367737 | 71 | 1392×718 | vp9 | 1 |

## 逐段画面检查

所有现有预览先完整解码，生成均匀抽帧、首尾帧及相邻帧差峰值的联系表；走路、坐下、起身和小跑片段另外每三帧取一帧。人工视觉结论只覆盖注明的采样帧，不能等同于逐帧人工播放全部视频或证明遮挡后的全部几何碰撞。

| 片段 | 查看内容与结果 | 问题帧号 / 证据 |
|---|---|---|
| A1_idle_night | 待机与首尾姿态稳定，未见明显边框或大面积透明孔洞。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/night/A1_idle/overview.png) |
| B2_wave_night | 挥手和回到中立姿态未见明显突跳，人物周边未见矩形暗框。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/night/B2_wave/overview.png) |
| B3_cheer_night | 欢呼中段的起跳属于动作本身；首尾回到站姿，未见明显异常跳变。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/night/B3_cheer/overview.png) |
| C3_fire_loop_night | 坐姿循环与首尾抽帧未见明显跳变或大面积破洞；火星、帽子和披风遮挡臀部接触位置，不能确认所有凳面接触。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/night/C3_fire_loop/focus.png) |
| C3_fire_in_night | 坐下过程未见明确大块破洞或边框；F23–41 身体前倾、披风和火星遮挡凳面接触，悬空/陷入关系保留复核。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/night/C3_fire_in/focus.png) |
| C3_fire_out_night | 起身和回到站姿未见明确突跳；凳面接触被衣物与火星部分遮挡。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/night/C3_fire_out/focus.png) |
| W_stand_fire_night | 查看绕过栅栏左端的移动路线，另查 F45 全画面，未见明确穿过栏杆；脚部部分被披风遮挡，细微脚滑未能完全排除。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/night/W_stand_fire/overview.png) |
| W_fire_stand_night | 返回路线和首尾抽帧未见明确穿过栅栏或突跳；不能排除细微脚滑。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/night/W_fire_stand/overview.png) |
| B4_rush_night | 另看 F107 全图与 F118–148 密集联系表，未见明确撞入台阶；F149–160 为脚本设计的渐隐，不判作突然消失；细微脚滑保留复核。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/night/B4_rush/overview.png) |
| A1_idle_morning | 站立待机和首尾抽帧稳定，未见明显人物暗框或破洞。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/morning/A1_idle/overview.png) |
| B2_wave_morning | 挥手与返回站姿未见明显突跳、矩形边框或大面积透明孔洞。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/morning/B2_wave/overview.png) |
| A3_stretch_morning | 伸展与恢复中立姿态未见明显首尾跳变，周围未见明显暗框。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/morning/A3_stretch/overview.png) |
| C1a_yawn_morning | 打哈欠与恢复站姿未见明确穿模、周围矩形边框或首尾突跳。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/morning/C1a_yawn/overview.png) |
| B3_cheer_morning | 欢呼、起跳和回到站姿未见明显异常；中段起跳为动作内容。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/morning/B3_cheer/overview.png) |
| C1b_water_morning | 浇花前倾和抬手未见明确把身体穿进箱体或大面积破洞；衣物遮挡了靠箱体的一部分接触区域。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/morning/C1b_water/overview.png) |
| W_stand_planter_morning | 移动到花箱端部，抽帧未见明确穿过箱体或台阶；不能排除细微脚滑。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/morning/W_stand_planter/overview.png) |
| W_planter_stand_morning | 从花箱端部返回，未见明确穿过箱体或首尾突跳；不能排除细微脚滑。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/morning/W_planter_stand/overview.png) |
| A1_idle_noon | 待机与首尾抽帧稳定，未见明显黑色颗粒、矩形暗框或大面积透明孔洞。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/noon/A1_idle/overview.png) |
| B2_wave_noon | 挥手过程未见明显边框、破洞或首尾突跳。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/noon/B2_wave/overview.png) |
| C2b_feed_noon | 撒食物动作与回到站姿未见明显异常，阴影随人物姿态变化，未见明确矩形暗框。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/noon/C2b_feed/overview.png) |
| B3_cheer_noon | 欢呼中段的起跳和转身为动作内容，首尾回到站姿，未见明确异常跳变。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/noon/B3_cheer/overview.png) |
| C3_fire_loop_noon | 另查原始 A_0001.png 与局部抽帧，白色衣饰为原始材质内容，未见大块透明孔洞；凳面接触部分仍被衣物遮挡。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/noon/C3_fire_loop/focus.png) |
| C3_fire_in_noon | 局部抽帧显示坐下和收拢双腿，未见明确大片破洞；F23–41 臀部接触被帽檐/披风遮挡，不能证明完全无悬空或陷入。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/noon/C3_fire_in/focus.png) |
| C3_fire_out_noon | 局部抽帧显示起身过程，未见明确大片破洞或首尾突跳；不对遮挡后的凳面碰撞作保证。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/noon/C3_fire_out/focus.png) |
| W_stand_fire_noon | 绕过栅栏左端移动，未见明确穿过栏杆；低分辨率预览及衣物遮挡使细微脚滑无法完全排除。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/noon/W_stand_fire/overview.png) |
| W_fire_stand_noon | 返回路线未见明确穿过栏杆或末尾突跳；细微脚滑无法完全排除。 | [抽帧截图](D:/gsd_island/output/qa/compose_20261116/review/noon/W_fire_stand/overview.png) |

## 错误和限制

文件参数与解码检查未记录错误。画面问题以逐段表为准。

本次使用既有原始帧，正式产物对应原始场景；boat_revision 中的木船试片未替换这些原始帧。没有下载、安装软件或上传、公开任何结果。

用户指定的六个预览位于 D:\gsd_island\output\video\：preview_C3_fire_in_night.mp4、preview_C3_fire_loop_night.mp4、preview_W_stand_fire_night.mp4、preview_B4_rush_night.mp4、preview_C1b_water_morning.mp4、preview_B3_cheer_noon.mp4。
