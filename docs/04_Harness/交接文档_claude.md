# 共生岛 · 项目交接文档（2026-11-11 更新）

## 1. 项目目标
- 课程项目：桌面日程管理应用，搭配 AI 虚拟角色（开题报告为 docx）。
- 视觉方案：用 Blender 预渲染精美岛屿场景和人物，做成循环动态桌面背景，通过 Wallpaper Engine **网页壁纸**叠加日程等内容，并按时间和日程自动切换人物动画。
- 人物风格定为「二次元 3A」级精度，不做 Q 版。以后的近景镜头采用预渲染片段。
- **当前阶段（2026-11-11）分两条线同时进行：**
  - **建模 / 渲染线**：Codex 在用户的 Windows 电脑上制作并渲染岛屿的 11 个人物动画片段（见 3.4）。
  - **功能线**：另开新对话做日程后端、壁纸播放器（状态机）、日程 UI、AI 角色对话，先用占位视频（见第 4 节）。

## 2. 目录结构（用户 Mac：`~/Desktop/共生岛/`）
```
共生岛/
├─ claude.md                               # 本交接文档的本地版
├─ 共生岛_场景与动作清单.md                 # 统一规范、场景、动作、一天的状态流程（第四节）
├─ Codex提示词.md                          # 发给 Codex 的 11 个片段制作和渲染提示词
├─ 共生岛_Codex动画渲染包.zip              # 给 Windows 的包（58MB，见 3.4）
├─ 共生岛开题报告_需求与项目规模_Blender方案.docx   # 报告最新版（改了 6.2/7.1/7.3）
├─ 动作/                                   # 21 个 Mixamo 动作 FBX（Breathing Idle、Waving 等）
├─ 动作预览/                               # 白模预览：每个动作一个 PNG 序列文件夹
│  └─ _视频/                               # 00_全部动作审核.mp4 + 每个动作单独 mp4
├─ docs/superpowers/                       # 魔法教室的设计 spec 和计划（另一个 AI 写的）
├─ win_render_v4/ + 共生岛_v4动画_Windows渲染包.zip   # v4 背景循环（含站立待机）的渲染包
└─ blender/
   ├─ gongshengdao_scene_v3.py / _v4.py    # 场景脚本（v4 exec v3 后重排布局）
   ├─ import_character.py / animate_loop.py
   ├─ build_anim_v4.py → gongshengdao_v4_anim.blend    # 当前动画工程（5.2 格式）
   ├─ prepare_farm_v4.py → farm_v4_{morning,noon,night}.blend
   ├─ retarget_mixamo.py                   # Mixamo 动作重定向到伊蕾娜 + 白模预览
   ├─ magic_classroom.py / classroom_parts/ / check_classroom.py → magic_classroom.blend
   ├─ characters/elaina/                   # YLN.fbx.part_00–05（需合并）+ 合并后的 fbx + textures/
   └─ render/                              # 各种预览图和日志
```

## 3. 已完成的功能
- 报告：表格和代码底色改成黑白，流程图排版优化；第 6.2、7.1、7.3 节改为 Blender + Wallpaper Engine 方案。
- 场景经历：草稿 → v2 卡通 → v3 风格化 PBR → v4 按效果图重排（见 3.1）。
- 人物：伊蕾娜 FBX 已导入，带卡通材质和描边，有 85mm 近景相机 CAM_closeup。
- 骨骼：FBX 里的 Auto-Rig Pro 约束丢失了，已解析 FBX 并重建骨骼链（23 根链骨，头发 16 组，衣摆 10 组）。
- 站立待机循环（A1）：呼吸、重心摇摆、看向四周、点头、眨眼、头发和衣摆摆动、袖口反向补偿。
- 环境循环：水面、烟、萤火虫、花瓣、雾、鸭子和船起伏、草和花随风弯曲、篝火（共 46 项以上）。

## 3.1 v4 场景（2026-11-05，参考用户给的像素风效果图 1:1 重排）
- `gongshengdao_scene_v4.py`：exec v3 后覆盖布局和夜景。`S(fx, fy, z)` 把效果图屏幕比例坐标换算成世界坐标；岛形按 OUTLINE_F 轮廓生成。
- 相机 az=-28，el=42，ortho=24（正交斜俯视）。木屋正面朝右下，门廊呈 L 形，左前角接码头。有石板路、野餐桌、拱桥和瀑布、对岸亮灯小屋、月亮、星星、水面碎光。
- 樱花树已去掉，原位置（屏幕 0.53, 0.80）换成篝火：石圈火塘、木柴、三根原木凳、三脚架吊锅，火苗第 1–193 帧无缝循环，只在夜里显示。
- 夜景：月光 1.05，环境光 0.55，灯笼 260W，窗户 320W，7 块暖色面光 + 1 块冷色月光补光；物体带 `gsd_show` 属性的按时段显示或隐藏。
- 石板路路径点：v4 脚本第 183–188 行的 main / back / toward_bridge 列表；门廊前花箱 planter*，码头 dock*，篝火 campfire*。
- 运行方式：在 Blender GUI 的 Python 控制台里用 subprocess.Popen 起一个 `bpy.app.binary_path -b ...` 后台进程（GUI 不加载大场景）。
- 背景循环渲染包：`共生岛_v4动画_Windows渲染包.zip`（三个 farm_v4 文件 + bat 脚本）。

## 3.2 魔法教室场景（2026-11-07，由另一个 AI 按我们给的提示词制作）
- `blender/magic_classroom.py`（+ `classroom_parts/`）→ `magic_classroom.blend`。Blender 5.2.3 验证：构建 6 秒，内存峰值约 1.1GB，约 37 万三角面，2291 个物体。
- 剖面小屋式正交斜俯视（去掉后墙、右墙、顶面），和岛屿同系列；另有 CAM_persp（35mm）和 CAM_closeup（85mm）。
- 黑板中央 60% 是干净深色区（材质 cls_board_ui），留给日程 UI；192 帧内悬浮物、星象仪对黑板 UI 区和人物位 C1 的遮挡为 0。
- 人物位 Empty：CHAR_SPOT_1（讲桌右侧）、CHAR_SPOT_2（窗边）。窗外背景板 cls_backdrop，可用 SHOW_BACKDROP 开关。
- 早 / 午 / 夜三套光照，`check_classroom.py` 做循环和遮挡验收（CLASSROOM_ACCEPTANCE_PASS）。
- 还没有放人物，也没有做 B5 听课动作。

## 3.3 岛屿动作白模预览（2026-11-10）
- `retarget_mixamo.py -- preview island`：把 15 个 Mixamo 动作套到伊蕾娜身上，Workbench 白模渲染到 `动作预览/<动作名>/`，合成 `动作预览/_视频/00_全部动作审核.mp4`（70 秒，带编号和名称）。
- 修了一个 bug：重定向时源场景的 depsgraph 可能为 None（Breathing Idle 报错），现在会先 update 视图层再取。
- 已知现象：白模里没有凳子，坐姿动作坐在空中；浇水、撒面包屑弯腰时帽子挡脸；走路、小跑是原地动作。

## 3.4 交给 Codex 的 11 个岛屿片段（2026-11-10）
- 渲染包：`共生岛_Codex动画渲染包.zip`，用户解压到 Windows 桌面，把里面的 `Codex提示词.md` 整段发给 Codex。
- 片段（前缀 / 时段）：A1_idle（早午夜，已有）、A2_walk（夜、早）、A3_stretch（早）、B2_wave（早午夜）、B3_cheer（早午夜）、B4_rush（夜）、C1a_yawn（早）、C1b_water（早）、C2a_dock_sit（午，循环）、C2b_feed（午）、C3_fire_in / loop / out（夜）。人物约 2,300 帧 + 背景 3×192 帧。
- 规范：一次性片段从中立姿势起止（首尾 12 帧过渡）；循环片段 192 帧首尾无缝；保留袖口补偿、眨眼、头发衣摆摆动。
- 渲染方式：背景每个时段只渲一次（不含人物）；人物片段只渲人物层（透明背景 + holdout 遮挡 + shadow catcher 影子），最后叠加。
- 流程有两个停顿点：场景内白模预览等用户逐个批准；每个时段先渲 1 帧报告耗时，用户确认后再渲全部。顺序：夜 → 早 → 午。
- 提醒 Codex：.blend 里的人物贴图可能指向 Mac 绝对路径，要先 find_missing_files。

## 4. 壁纸切换逻辑和接口约定（功能线用）
### 4.1 三层结构
| 层 | 内容 | 什么时候换 |
|---|---|---|
| 背景层 | bg_morning / bg_noon / bg_night 三段 8 秒循环 mp4 | 跨时段时交叉淡化 2–3 秒 |
| 人物层 | 各片段的透明 WebM（VP9 yuva420p） | 状态机决定 |
| 界面层 | 日程卡片、提醒气泡（HTML） | 跟随日程数据 |

PNG 序列转透明 WebM：`ffmpeg -framerate 24 -i frame_%04d.png -c:v libvpx-vp9 -pix_fmt yuva420p -b:v 4M <片段>_<时段>.webm`

### 4.2 状态机
- 优先级：**事件动作**（提醒→B2 挥手，完成→B3 欢呼，截止风险→B4 小跑）＞ **日程状态**（有课→学院，学习任务→室内）＞ **时段默认**（早 A1 待机 + 偶尔 C1；午 C2a 码头晃脚；夜 C3 篝火）。
- 只在当前片段播完时切换（所有片段都在中立姿势起止），新状态先排队。
- 不同位置之间必须经过走路片段。位置图：默认站位 ↔ 篝火 ↔ 木屋门口，默认站位 ↔ 码头，默认站位 ↔ 花箱。
- 坐着时（篝火、码头）事件只弹气泡，或先播站起来再播事件动作。
- 两个 `<video>` 元素交替，预加载下一段，在 ended 时切换，避免卡顿。
- 日程数据：日程应用在本机开接口（例如 127.0.0.1:8765，HTTP 查状态 + WebSocket 推事件），壁纸轮询或订阅。

### 4.3 接口约定（建模线和功能线都要遵守）
- 文件命名：`{片段前缀}_{时段}.webm`、`bg_{时段}.mp4`，前缀和 3.4 一致。
- clips.json：每个片段的位置、帧数、是否循环、起止位置；播放器只读这个文件，不写死片段名。
- 视频规格：2560×1440，24fps。
- 事件名：reminder、done、deadline_risk、class_start 等。
- 位置图里还缺 3 段走路：篝火→默认站位回程（A2_back）、默认站位↔码头、默认站位↔花箱。clips.json 先登记，Codex 到停顿点 1 时补做。

## 5. 关键技术栈
- Blender 5.2（用户 Mac M1 Pro，16GB；Windows 电脑负责正式渲染）。脚本都用 bpy/bmesh 写，用 `blender -b -P` 无界面运行。
- EEVEE Next。5.x 版合成器用 `scene.compositing_node_group`。AgX + "AgX - Punchy"，Glare(Bloom)。
- 粒子实例化做植被，Simple Deform 修改器做风动。Freestyle 描边只作用于人物集合。
- 视图层：BG / FG（holdout）/ CHAR；集合名 FG_前景遮挡、CHAR_人物、LIGHTS_灯光。
- 动作：5.x 是分层 action，4.x 用 `action.fcurves`。F 曲线加 Cyclic 修改器实现循环。
- 云渲染平台调研（11-04，现已改为用户自己的 Windows 电脑渲染，仅作备查）：Render Elf 最高 4.5.1；瑞云需镭速；SheepIt 连不上；渲染101 只确认到 5.0；国外 blender.farm / Megarender / RenderStreet / Super Renders Farm 支持 5.2；国内可租 AutoDL / 恒源云 / 智星云 GPU。

## 6. 重要文件说明
- `gongshengdao_scene_v3.py`：入口 `build()`；`GSD_ATTACH=True` 时只运行 `rebind()`；`apply_time(t)` 切换时段。
- `import_character.py`：`ensure_fbx()` 合并分卷 FBX，md5 应为 2397966c4927de44101da895633e3113；人物层级 CHAR_root → CHAR_fit，身高 1.55；位置和相机方位从 builtins.GSD_CHAR_POS / GSD_CAM_AZ 读取。
- `animate_loop.py`：`fix_hierarchy()` 按 CHAIN 字典重建父子关系；姿势旋转公式 R⁻¹·A·R（静置骨架空间）。
- `retarget_mixamo.py`：`-- preview island|indoor|all|"<动作名>"`；手臂先对齐 A 字 / T 字静止方向再套转动；走路、小跑原地化（IN_PLACE）。注意：每次运行会清空 `动作预览/log.txt`。
- `speed.py`：草稿 / 最低 / 最终画质切换。

## 7. 已知问题
- 所有 .blend 都是 5.2 格式，低版本打不开。
- 在 Blender GUI 里跑完整场景会占用约 32GB 内存并卡死，必须用无界面运行。
- 用电脑控制操作 Blender 时，输入命令后工具调用常常 60 秒超时，但命令其实已经执行；要去检查输出文件，不要重复执行。
- device_commit 偶尔没有真正覆盖文件，提交后要用 device_list_dir 核对文件大小。
- 「只渲人物层再叠加」在 EEVEE 5.2 里的阴影和遮挡还没实测过。
- 伊蕾娜出自《魔女之旅》（版权方白石定规 / SB Creative），**只能用于非商业课程演示**。

## 8. 下一步
1. 建模线：跟进 Codex 的停顿点 1（场景内白模预览，逐个批准），让它补做 3 段走路；停顿点 2 看单帧耗时后再全量渲染。
2. 功能线（新对话）：技术选型 → 日程后端 + 本机接口 → 壁纸播放器状态机 + clips.json → 占位视频 → 调试面板（改虚拟时间、手动触发事件）→ 日程 UI → AI 角色对话。
3. 成品视频出来后替换占位视频，联调。
4. 之后：木屋室内场景（自习、睡觉、起床流程，P0）、魔法教室放人物 + B5 听课、骑扫帚过渡、深夜熄灯版。

## 9. 约束 / 注意事项
- 报告只改用户点名的章节，其它部分不能动。
- 人物保持二次元 3A 精致风格，不做 Q 版。
- 动画参数固定：8 秒，24fps，192 帧，首尾循环。
- 不替用户输入密码或支付信息。下载文件、付费操作、提交表单都要先得到用户明确同意。不点击系统弹窗（比如「移到废纸篓」）。
- 不能直接在 GUI 里构建高精度场景（16GB 内存会爆），用 `-b` 无界面运行。
- 修改材质颜色要先做 sRGB→线性转换（`lin()`），否则颜色会发灰。
- 用户打开浏览器时偏好用 SunBrowser。
