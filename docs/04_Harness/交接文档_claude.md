# 共生岛 · 建模 / 动画 / 渲染 交接文档（2026-11-11，11-23 更新）

> 这份文档给接手**建模、动画、渲染**的新对话。功能开发（课表识别、排程、AI 聊天、桌面播放器）在另外的对话里做，不在这里。
> 读完本文就能接着干。更细的规范在仓库 `gongshengdao/docs/`（见第 9 节）。

---

## 1. 项目一句话
大学生桌面日程应用「共生岛」（课程项目）：课表导入 → 今日待办 → AI 人物聊天。桌面上是一座会随早 / 午 / 夜变化的岛屿，人物伊蕾娜按日程在岛上活动。
美术方案：**Blender 预渲染**，桌面端只播放视频——背景每个时段一段 8 秒无缝循环，人物每个动作一段**透明 WebM**，叠在背景上，由状态机按日程切换（ADR-003）。

## 2. 当前状态（一眼看懂）
| 部分 | 状态 |
|---|---|
| 岛屿场景 v4（早 / 午 / 夜三套光照，篝火、拱桥、瀑布、码头、灯笼等） | ✅ 完成 |
| 人物：导入、卡通材质与描边、骨骼链重建、站立待机 192 帧循环 | ✅ 完成 |
| 15 个 Mixamo 动作重定向到伊蕾娜 | ✅ 完成 |
| 斗篷物理摆动（cloth_sim v2） | ✅ 完成，用户已认可效果 |
| **岛屿最终版 15 个人物片段**（首尾闭合、走路路径、坐凳子、衣摆） | ✅ 构建完成，闭合检查全部为 0 |
| 渲染 / 合成流水线（裁剪渲染 + 遮罩 + 比值阴影 → 透明 WebM） | ✅ 在 Mac 上端到端验证通过 |
| **Windows 正式渲染与合成** | ✅ 2026-11-16 完成：3 段背景 + 26 段人物 WebM + 26 段预览 + 3 份清单，0 错误（成品在用户 Windows `D:\gsd_island\output\video\`）。渲染改动：Freestyle → 反转外壳描边（130h → 6.5h）、面光关投影、白天隐藏萤火虫、遮罩忽略火星、合成 box 变量 bug 已修 |
| 成品审核 | 🟡 Codex 抽帧检查 26 段未见明显穿模、方框、破洞；**坐凳接触、细微脚滑待看 preview 视频确认** |
| 魔法教室场景 | ✅ 场景完成（另一个 AI 按我们的画风提示词做的） |
| **魔法教室人物动画** | ✅ 2026-11-18 Windows 渲染与合成完成，11-22 复核通过：伊蕾娜 B5_listen 听课循环 + 老师 T1_lecture 讲课循环（576 帧）/ T2_pace 踱步（441 帧），三层渲染（背景 / 伊蕾娜 / 老师）。详见 `docs/04_Harness/魔法教室交接.md`；老师头发 / 裙带 / 蝶翼摆动未做 |
| 木屋室内（自习、睡觉、起床） | 🟡 2026-11-25 布局白模 v1 + 侧睡静帧用户认可（分支 `feat/cabin-interior`，详见 `docs/04_Harness/木屋室内交接.md`）；灯光调色交给 Windows Codex（`Codex提示词_室内.md`）；动作片段未开始 |

## 3. 硬约束（必须遵守）
- **Blender 5.2**。所有 .blend 是 5.2 格式，4.x 打不开；不要用低版本保存。
- **一律无界面运行** `blender -b [x.blend] -P 脚本.py -- 参数`。在 GUI 里构建完整场景会占用约 32GB 内存卡死（用户 Mac 是 M1 Pro 16GB）。
- **人物保持「二次元 3A」精度，不做 Q 版**。用户考虑过换成方块人，最后明确决定**继续用伊蕾娜**。
- **动画规格固定**：2560×1440，24fps；循环片段 192 帧，第 193 帧 = 第 1 帧；一次性片段从「中立站姿」开始并结束（= 站立待机 A1 第 1 帧）；坐姿片段以「中立坐姿」（= C3_fire_loop 第 1 帧）衔接；头尾 12 帧过渡。
- **环境动画必须是 192 帧整周期**（Cyclic 修改器或整数频率正弦）。不能用不周期的噪声——会破坏背景循环，也会让人物层合成出错。
- **改材质颜色先做 sRGB → 线性转换**（`lin()`），否则发灰。
- **不替用户输入密码、付款信息**；下载、付费、提交表单先问；不点系统弹窗（如「移到废纸篓」）。
- **大任务先给白模 / 方案，用户批准后再做成品**；渲染先试 1 帧报告耗时，用户确认再全量。
- 伊蕾娜出自《魔女之旅》（白石定规 / SB Creative），**只用于非商业课程演示**；人物模型不进 Git，渲染结果不公开发布。

## 4. 文件在哪（用户 Mac：`~/Desktop/共生岛/`）
```
共生岛/
├─ claude.md / 建模交接文档.md        本交接文档的本地副本（以仓库 docs/04_Harness/交接文档_claude.md 为准，改完同步过来）
├─ 共生岛_场景与动作清单.md           动作清单、一天的状态流程、制作顺序（原始规划）
├─ 共生岛开题报告.docx                开题报告（用户已改名，原「_Blender方案」版）
├─ 共生岛_岛屿最终版_Windows渲染包.zip   岛屿最终版 Windows 渲染包（84MB，已渲染完成）
├─ 共生岛_魔法教室_Windows渲染包_v2.zip  魔法教室 Windows 渲染包 v2（已渲染完成）
├─ 动作/                             19 个 Mixamo 动作 FBX + _probe.json（每个动作的帧数、臀部轨迹）
├─ 动作预览/、动作预览_衣摆/          白模预览、衣摆 v1/v2 对比视频与抽帧
├─ gongshengdao/                     ★ Git 仓库（文档 + 脚本 + 评测证据，见第 9 节）
├─ 备份_20261103/                    旧版脚本备份（改脚本前先备份到这里）
├─ _to_delete/                       待用户手动删除的文件
└─ blender/
   ├─ gongshengdao_scene_v3.py / _v4.py      场景（v4 exec v3 后重排；GSD_ATTACH=True 时只重新绑定不重建）
   ├─ import_character.py                    人物导入（分卷 FBX 合并，md5 2397966c4927de44101da895633e3113）
   ├─ animate_loop.py                        骨骼链重建 + 站立待机 + 环境动画 → build_anim_v4.py 生成 gongshengdao_v4_anim.blend
   ├─ gongshengdao_v4_anim.blend             ★ 动画工程：v4 场景 + 人物 + 待机（所有片段构建的起点）
   ├─ retarget_mixamo.py                     Mixamo 重定向；`-- preview island` 出白模；`-- lib` 作为库被调用
   ├─ cloth_sim.py                           斗篷弹簧摆（v2 参数）；cloth_sim_v1.py 是第一版
   ├─ magic_classroom.py + classroom_parts/ + check_classroom.py → magic_classroom.blend
   ├─ classroom_anim/                        ★ 魔法教室人物动画（详见 docs/04_Harness/魔法教室交接.md）
   │  ├─ build_classroom.py / teacher.py / board_chalk.py   构建 B5 / T1 / T2、老师、板书 → classroom_anim.blend
   │  ├─ pack_classroom.py                   裁剪框 + 清单 + 打包 → winpkg_build/classroom.blend
   │  ├─ scripts/render_classroom.py / compose_classroom.py   三层渲染与合成
   │  └─ *_v1…v5.py、whitebox_v1…v10/        旧版本脚本与白模（仓库里只有最终版）
   ├─ _launch.py                             后台启动器（只在没有本机终端时用，见第 6 节）
   ├─ characters/elaina/                     人物模型与贴图（有版权，不进 Git）
   ├─ characters/teacher/Untitled.fbx        老师 MMD 模型（用户提供，版权素材，不进 Git）
   ├─ farm_*.blend、gongshengdao_v45.blend   旧方案产物（已废弃，可清理）
   └─ island_final/                          ★ 岛屿最终版
      ├─ build_clips.py                      构建 15 个片段 → island_{morning,noon,night}.blend + clips_*.json + closure_report.json
      ├─ island_{morning,noon,night}.blend   三个时段的渲染文件（各 28MB，贴图已打包，含全部片段动作）
      ├─ clips_{morning,noon,night}.json     片段清单（帧数、循环、起止位置、裁剪区域）
      ├─ scripts/render_island.py            渲染：bg / clips / masks / all / test，断点续渲
      ├─ scripts/compose_island.py           合成：透明 PNG、WebM、预览 MP4、背景 MP4
      ├─ winpkg/                             Windows 批处理 + 说明.txt
      ├─ whitebox.py / whitebox_all.py       场景内白模预览（Workbench）
      ├─ probe_scene.py / probe.json / top.png   场景坐标探测、俯视图（1 米网格）
      ├─ job.json                            后台任务参数（见第 6 节）
      ├─ build_log.txt                       构建日志
      └─ output/ check/ whitebox/            Mac 上的测试输出（可删）
```

## 5. 岛屿最终版：片段与位置
### 5.1 位置（世界坐标，CHAR_root）
| 名称 | 位置 | 朝向 | 说明 |
|---|---|---|---|
| stand | (-1.623, 0.574, 0.45) | −28°（面向镜头） | 门廊台阶前的默认站位 |
| fire | (-0.316, -3.600, 0.437) | −28°（面向篝火） | 篝火北侧原木凳 seat0 前 0.53 m；凳面高 0.849 |
| planter | (-5.187, 1.334, 0.431) | −75.7°（面向花箱） | 门廊前 planter3 东端 |
| door | (-2.973, 4.164, 0.74) | 180° | 木屋门口（门廊上） |

朝向公式：`heading = atan2(dx, -dy)`（人物默认面朝 (sin h, −cos h)）。

### 5.2 15 个片段
| 片段 | 帧数 | 类型 | 位置 | 时段 | 来源 |
|---|---|---|---|---|---|
| A1_idle | 192 | 循环 | stand | 早午夜 | animate_loop 待机 |
| B2_wave | 77 | 一次性 | stand | 早午夜 | Waving |
| B3_cheer | 79 | 一次性 | stand | 早午夜 | Joyful Jump + Victory Idle（交叉 10 帧） |
| A3_stretch | 214 | 一次性 | stand | 早 | Arm Stretching |
| C1a_yawn | 201 | 一次性 | stand | 早 | Yawn |
| C2b_feed | 135 | 一次性 | stand | 午 | Throwing（原地化） |
| C1b_water | 135 | 一次性 | planter | 早 | Watering（原地化） |
| W_stand_planter / W_planter_stand | 71 / 71 | 走路 | stand ↔ planter | 早 | Happy Walk + 路径 |
| W_stand_fire / W_fire_stand | 111 / 111 | 走路 | stand ↔ fire | 午夜 | Happy Walk + 路径 |
| C3_fire_in | 55 | 站 → 坐 | fire | 午夜 | Stand To Sit |
| C3_fire_loop | 192 | 循环（坐） | fire | 午夜 | **Sitting**（不是 Sitting Idle，那个是坐地上的） |
| C3_fire_out | 55 | 坐 → 站 | fire | 午夜 | Sit To Stand |
| B4_rush | 160 | 小跑 | fire → door | 夜 | Jogging + 路径，最后 14 帧站定，合成时淡出 12 帧 |

各时段数量：早 8 段、午 9 段、夜 9 段，共 26 段。

### 5.3 关键做法（`build_clips.py`）
- 重定向用 `retarget_mixamo.py` 的 lib 模式（`sys.argv = [..., "--", "lib"]` 后 exec），`LAST` 里有比例 k、臀部逐帧位移、漂移量。
- 一次性片段：首尾 12 帧和中立姿势混合（`ease(i/RAMP)`，首帧权重为 0，所以首尾严格等于中立姿势）。
- 循环（C3_fire_loop）：Sitting 从第 25 帧截 192 帧，最后 24 帧和开头交叉淡化。
- 走路：步伐相位按**实际移动距离**推进（起步 / 停步时步子变慢，不滑步）；路径 Chaikin 平滑，地面高度用射线检测 `island_top`、`path_*`、`house_porch_*`、`house_step*`、`campfire_ground`；头尾 16 帧平滑转身。
- 坐下：按臀部高度算坐下进度 p，修正量在「站立对齐」和「坐姿对齐」之间过渡，坐姿目标 = 凳面 + 0.10 m。
- 衣摆：`cloth_sim.simulate(..., pin_start, pin_end)`，头尾钉到相邻片段的衣摆姿势。
- 篝火路径要绕开：北侧两根原木凳（seat2、seat0）几乎首尾相接，东北有栅栏 fence7 → 从东侧绕进凳子和火之间。路径点见 `build_clips.py` 的 `P_FIRE`、`P_PL`、`P_DOOR`。
- 构建末尾会给所有环境曲线补 Cyclic，夜里灯笼闪烁改为整数频率正弦（23、41 次 / 192 帧）。
- 裁剪区域：每帧取人物关键点 + 帽子 + 斗篷尖，按该时段的太阳方向和 7 m 内点光源算影子落点，投影到镜头，留 48 px 边距。

### 5.4 渲染与合成原理（ADR-006）
- 背景：隐藏 CHAR_人物 集合，整幅渲染 192 帧。
- 人物：只渲裁剪区域（`use_border + use_crop_to_border`），场景、光照、描边和背景完全相同。
- 遮罩：Workbench，人物白、其余黑（大体积 / 雾 / 天空等隐藏），几秒钟一帧。
- 合成：同一帧「有人物 ÷ 背景（第 ((f−1) mod 192)+1 帧）」= 阴影比例；变暗量 < 0.05 视为噪点；人物外扩 2 px 不算阴影；开运算（腐蚀 2 → 膨胀 2）去掉物体边缘细线；裁剪边缘 16 px 渐隐。
- 编码用 Blender 自带 FFmpeg（VSE）：WebM VP9 + RGBA（已验证 alpha_mode=1），背景 H.264。

## 6. 怎么在用户 Mac 上跑 Blender（重要）
### 6.1 在 Claude Code（桌面 App 的 Code 页 / 终端）里：直接运行（首选）
Claude Code 的 Bash 就跑在用户 Mac 上，可以直接调用 Blender（`/Applications/Blender.app`，5.2.3 LTS），不需要电脑控制：
```bash
BL=/Applications/Blender.app/Contents/MacOS/Blender
cd ~/Desktop/共生岛/blender
"$BL" -b gongshengdao_v4_anim.blend -P island_final/build_clips.py > island_final/build_stdout.txt 2>&1
```
- 构建、白模这类超过 2 分钟的任务放后台跑（Bash 的 run_in_background），结束后看 `build_log.txt` / stdout。
- 同一时间只跑一个 Blender 进程（16GB 内存）。
- 仓库可以直接在 `gongshengdao/` 里 `git commit`（见第 9 节）。

### 6.2 在 claude.ai 网页对话里：电脑控制 + device_bash（备用）
网页对话通过「电脑控制」操作用户的 Blender，通过 device_bash 读写文件。device_bash 运行在一台 Linux 虚拟机里，**不能直接运行 Mac 上的 Blender**。所以用这个办法：
1. 用 device_bash 写好 `blender/island_final/job.json`：
   ```json
   {"name": "build", "args": ["{B}/gongshengdao_v4_anim.blend", "-P", "{B}/island_final/build_clips.py"], "log": "build_stdout.txt"}
   ```
   `{B}` 会替换成 `~/Desktop/共生岛/blender`，`{P}` 替换成 `~/Desktop/共生岛`。
2. 在 Blender GUI 的 Python 控制台（Shift+F4 切换）里执行一次：
   ```python
   import os; D=os.path.expanduser('~/Desktop'); LAUNCH_DIR=[os.path.join(D,d,'blender') for d in os.listdir(D) if os.path.exists(os.path.join(D,d,'blender','_launch.py'))][0]; exec(open(os.path.join(LAUNCH_DIR,'_launch.py'),encoding='utf-8').read())
   ```
   之后每次只要按「↑」+ 回车重跑；控制台里的 `proc.kill()` 可以终止当前后台任务。
3. 用 device_bash 看 `island_final/<log>` 和输出文件。

注意（6.2 方式）：
- 电脑控制的批量操作经常 **60 秒超时，但命令其实已经执行**——先查日志 / 输出文件，不要重复执行。
- 电脑控制权限 30 分钟不用会过期，要重新申请（resolve_access → request_access）。
- Blender 刚打开时有启动画面，先点空白处关掉，再把鼠标移到视口按 Shift+F4。
- device_commit 偶尔没真正覆盖文件，提交后用 device_list_dir 核对大小。
- 用户说过：打开浏览器用 SunBrowser。

两种方式都适用：
- Mac 上 EEVEE 很慢：夜景 25% 分辨率 8 采样约 110–140 秒一帧（换反转外壳描边后约 6.5 秒）。**Mac 只做构建和 Workbench 白模（约 1 秒一帧），EEVEE 正式渲染交给 Windows**（RTX 5060，用户自己运行 winpkg 批处理，成品在 `D:\gsd_island\`、`D:\gsd_classroom_v2\`）。

## 7. 下一步（按优先级）
1. **看岛屿 preview 视频逐段审核**（规约 SPEC-DS-7，唯一未关闭的岛屿验收项；preview 在用户 Windows `D:\gsd_island\output\video\preview_*.mp4`，需要用户拷过来）：重点是
   - C3 三段：坐下时臀部是否贴凳面、腿和斗篷是否穿进原木凳；
   - 走路：绕篝火路径是否擦到原木凳 seat0 东端 / seat1、栅栏；上台阶、上门廊时脚是否贴合（B4_rush）；
   - C1b_water：是否穿进花箱；planter 位置离 planter1 只有约 0.4 m；
   - 弯腰动作（浇水、撒面包屑）帽子挡脸的程度；
   - 合成：人物周围有没有方框、闪烁的暗斑、假阴影。
   有问题就改 `build_clips.py`（位置、路径点、坐姿目标 +0.10、RAMP 等），重新构建 → 只重渲出问题的片段（`render_island.py -- clips --clips 名字`，先删掉该片段的 raw 目录）→ 重新合成。
2. **木屋室内场景**（P0，布局已认可，见 `木屋室内交接.md`）：自习（B1 学习循环）、睡觉流程（D1 上床、D2 睡觉循环）、起床流程（G1–G7）。镜头要和岛屿同风格（剖面小屋、正交斜俯视）；床和衣帽钩是睡觉、起床共用的。流程照搬岛屿最终版 / 魔法教室（中立姿势、闭合检查、衣摆、裁剪渲染）。
3. 魔法教室补充（可选）：老师头发 / 裙带 / 蝶翼摆动，做完只重渲老师 T1、T2 两段。
4. 其他：岛屿深夜熄灯版、骑扫帚过渡、彩蛋动作（见动作清单）。
5. ~~魔法教室放人物~~（11-18 完成，见 `魔法教室交接.md`）；~~Windows 正式渲染~~（11-16 完成）。

## 8. 已知问题与经验
- 原始 FBX 的 Auto-Rig Pro 约束丢失，已在 `animate_loop.fix_hierarchy()` 用 CHAIN 字典重建父子关系。姿势旋转公式 R⁻¹·A·R（静置骨架空间）。
- 袖口（forearm_twist.* 下的 Bone.085/099）必须反向补偿，否则袖子横到腰前；`retarget_mixamo.py` 已处理。
- 斗篷 6 条链（Bone.075/077/078/096/093/088，按绕身体一圈的顺序）都挂在 spine_01 上；cloth_sim v1 太松（横甩、撕成条），v2：STIFF (0.34, 0.24, 0.17)、DAMP 0.72、最大摆角 (14, 20, 26)°、相邻链拉平 0.45。
- 人物的短裙**没有单独骨骼**（跟着腿和胯动），要摆动需要先加骨骼。
- 码头在主镜头最左边缘、大半在画面外，并且会被桌面图标挡住 → 不在码头安排活动（ADR-007）。
- 俯视 Workbench 图里原木凳不显示（原因未查），但主镜头里正常。
- Mixamo「Sitting Idle」是坐在地上，坐凳子用「Sitting」；「Sitting_edge」臀部高 0.9 m，适合高台边缘晃腿。
- 合成第一版有物体边缘的细线假阴影，加开运算后解决（对比图在 `gongshengdao/evidence/island_final/compose_check.jpg`）。
- 5.x 动作 API：`action.fcurves` 不存在；写曲线前必须先把动作分配给对象，否则 `fcurve_ensure_for_datablock` 报错。
- 旧方案（已废弃，不要再用）：v4 渲染包 `共生岛_v4动画_Windows渲染包.zip`（背景里带人物）、Codex 渲染包 `共生岛_Codex动画渲染包.zip`（让 Codex 自己做动画的方案）、各云渲染平台（`共生岛_瑞云渲染包.zip`、`瑞云渲染包/`）、`blender/farm_*.blend`、`prepare_farm*.py`。
- 教室光尘（`cls_dust_*`、shaft、volume）会在遮罩上打孔，教室 v1 渲染因此作废；遮罩必须排除这些物体（`render_classroom.py` 已处理）。
- 循环片段可以是 192 的整数倍（如老师 T1_lecture 576 帧 = 3 个背景周期），这样叠在背景任意相位上仍然对得上。

## 9. Git 仓库 `共生岛/gongshengdao/`
- 内容：`docs/`（需求、验收规约、前置调研 + ADR-001~007、Harness 六份规范 + 两份交接文档、Global / Plan / Tasks、项目目录）、`blender/`（全部脚本，含 `classroom_anim/`）、`evidence/`（闭合检查、合成检查、日志、预览、教室成品检查报告）。
- 远程仓库：GitHub `https://github.com/seobang564-web/gongshengdao`（公开，用户确认过原样公开）。
- **改脚本后要同步进仓库**（把 `~/Desktop/共生岛/blender/` 里改好的脚本复制到 `gongshengdao/blender/` 对应位置）。
- **在 Claude Code 里**：直接在 `gongshengdao/` 里 `git commit`；推送用 `git push`（本机 git 用 osxkeychain 存凭据；能否免输密码推送未验证，要输密码时让用户自己来）。提交、推送前先问用户。
- **在 claude.ai 网页对话里**：claude.ai 已连接 GitHub，可用 add_repo 拿推送权限，从云端克隆推送。这个文件夹在 device_bash 里不能删除文件，直接在里面 `git commit` 会留下锁文件报错。做法是在虚拟机里 `git clone` 一份到 `$HOME`，复制改好的文件、提交，再用 `rsync -a --exclude .git/config ./ <仓库目录>/` 同步回去（排除 config 是为了保留用户的远程地址）。或者先向用户申请删除权限。推到 GitHub：在虚拟机仓库里 `git bundle create <共生岛>/_to_delete/x.bundle main`，暂存到云端后 fetch 进克隆再 push。
- 提交信息格式：`<类型>(<范围>): <说明>`，作者「方舒煜 <seobang564@gmail.com>」。
- `.gitignore` 已排除 .blend、渲染帧、视频、zip、人物模型、Mixamo FBX。

## 10. 和功能开发对话的接口
桌面播放器只读 `output/video/clips_<时段>.json`：
```json
{"time": "night", "background": "bg_night.mp4", "loop_frames": 192, "fps": 24, "resolution": [2560, 1440],
 "positions": {"stand": [...], "fire": [...], "planter": [...], "door": [...]},
 "clips": [{"name": "C3_fire_in", "file": "C3_fire_in_night.webm", "frames": 55, "loop": false,
            "from": "fire", "to": "fire", "pose_from": "stand", "pose_to": "seat",
            "x": 0, "y": 0, "w": 0, "h": 0, "fade_out": 0}]}
```
x / y 是人物层在 2560×1440 画面里的左上角坐标。新增片段时保持这个格式和命名（`<编号>_<动作>`，走路用 `W_<起点>_<终点>`），功能那边就不用改代码。

魔法教室的 `clips_classroom.json` 是同一格式的扩展：`"time": "classroom"`，顶层多一个 `"layers": ["elaina", "teacher"]`，每个片段多一个 `"layer"` 字段，桌面端按层分别播放（伊蕾娜层 B5_listen 循环；老师层 T1_lecture 循环，播完一圈可切 T2_pace，T2 播完回 T1）。岛屿清单没有 `layer` 字段，按单层处理。
