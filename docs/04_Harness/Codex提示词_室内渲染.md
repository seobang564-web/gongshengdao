# 给 Windows Codex 的提示词 · 木屋室内正式渲染与合成（2026-11-26）

> 取代 `Codex提示词_室内.md`（那份是 11-25 的灯光调色任务，夜里的灯光规则已经变了，以本文件为准）。
>
> **用法**
> 1. Windows 上：`git fetch`，`git checkout feat/cabin-interior`，`git pull`。
> 2. 准备两样不进 Git 的东西（人物有版权 / Mixamo 原始文件）：
>    - 岛屿三个渲染文件 `island_night.blend`、`island_morning.blend`、`island_noon.blend`（岛屿 Windows 渲染包里那三个，带人物和贴图）。
>    - 4 个 Mixamo 动作 FBX：`Typing.fbx`、`Laying Sleeping.fbx`、`Stand To Sit.fbx`、`Happy Walk.fbx`
>      （在 Mac 的 `~/Desktop/共生岛/动作/` 里；Windows 上没有的话从 Mac 拷过去，例如放到 `D:\gsd_cabin\动作\`）。
> 3. 把下面「提示词」整段发给 Codex，并告诉它上面两样东西在 Windows 上的实际路径。

---

## 提示词

你在做大学生桌面日程应用「共生岛」的美术部分。仓库 `gongshengdao`，分支 `feat/cabin-interior`。先读：
- `docs/04_Harness/木屋室内交接.md`（木屋室内：场景、站位、用户定下的规则、片段）
- `docs/04_Harness/交接文档_claude.md`（项目总览：第 3 节硬约束，第 5.4 节渲染与合成原理）
- `blender/cabin_interior/cabin_whitebox.py`（从零搭场景 + 构建全部人物片段的脚本；末尾的 `CLIPS_CABIN`、`BG_VARIANTS`、`play_clip()`）
- 参考成品：岛屿 `blender/island_final/scripts/render_island.py`、`compose_island.py`；魔法教室 `blender/classroom_anim/scripts/`

**分工**：场景几何、家具、人物姿势和动画由 Mac 上的 Claude 负责，你**不要改**（发现动画 / 穿模问题写进报告，由 Claude 改）。你负责：在 Windows 上重建场景、正式 EEVEE 渲染、合成透明 WebM、清单、成品检查。

### 0. 环境变量（脚本靠这几个找外部文件）
```
set GSD_CHAR_SRC=<island_night.blend 的完整路径>
set GSD_MIXAMO_DIR=<放 4 个 FBX 的文件夹>
```
`retarget_mixamo.py`、`cloth_sim.py` 用仓库 `blender/` 里那两份，不用设。

### 1. 窗外岛屿背景板（书桌机位从窗户看出去用）
对 night / morning / noon 三个岛屿文件各跑一次（输出到 `blender/cabin_interior/backdrop/`，不进 Git）：
```
blender -b <island_night.blend>   -P blender/cabin_interior/render_window_bg.py -- --tag night   --pct 100 --samples 64 --views front,west
blender -b <island_morning.blend> -P blender/cabin_interior/render_window_bg.py -- --tag morning --pct 100 --samples 64 --views front,west
blender -b <island_noon.blend>    -P blender/cabin_interior/render_window_bg.py -- --tag noon    --pct 100 --samples 64 --views front,west
```

### 2. 先在 Windows 上完整构建一次，确认能跑通
```
blender -b --factory-startup -P blender/cabin_interior/cabin_whitebox.py -- --b1 --wb-only --morning-wb --walk-wb --a4-wb --b1-wb
```
- 输出在 `blender/cabin_interior/whitebox/v1/`：`build_log.txt`、`clips_cabin.json`（片段清单）、各片段白模 mp4、`cabin_whitebox.blend`。
- 对照 `build_log.txt` 检查：没有 Traceback；`G5 戴帽 v5（魔法）… 手的 IK 误差` 在 1 cm 内；`B6 v2（…）` 两个机位都有；14 段片段帧数和清单一致。
- 把白模 mp4 抽几帧和 Mac 版对比（仓库 `evidence/cabin_interior/` 里有检查图），确认动作一致再往下做。

### 3. 写渲染脚本 `blender/cabin_interior/scripts/render_cabin.py`
**不要打开存好的 .blend 再自己切状态**——切片段的逻辑都在 Python 函数里。正确做法：在你的脚本里 exec 场景脚本，再调用它的函数：
```python
import sys
S = r"<仓库>/blender/cabin_interior/cabin_whitebox.py"
sys.argv = [sys.argv[0], "--", "--b1", "--wb-only"]
G = {"__name__": "__main__", "__file__": S}
exec(compile(open(S, encoding="utf-8").read(), S, "exec"), G)   # 内存里搭好场景 + 全部片段动作
for c in G["CLIPS_CABIN"]:
    for cam in c["cams"]:
        nf = G["play_clip"](c["name"], cam)   # 设好时段光照、镜头、显示哪份人物、全部动作、B6 特效；返回帧数
        ...                                    # 渲第 1..nf 帧
```
`play_clip` 之后再按需要把引擎切回 EEVEE、设采样数（它不改渲染设置；场景脚本的 `--wb-only` 只是不出它自己的 EEVEE 测试图）。

**三层输出（原理同岛屿 ADR-006）**
1. **背景**：按 `BG_VARIANTS` × 用到它的机位，每个 192 帧无缝循环（深夜屏幕微闪、被子呼吸都是 192 帧整周期）。
   - 藏掉全部人物集合（`CH_INFO[*]["coll"]`）和 `FX_B6_*` 集合。
   - 按变体设道具：`curtain_mode("closed"/"open")`（东窗 win_l2）、`hat_mode("stand"/"head")`（`head` = 衣帽架空着，背景里不要人物）、椅子停在 `B1_CHAIR_XY`。
   - 主镜头 `CAM_main`：night、late、dawn_closed、dawn_open、dawn_open_nohat；书桌机位 `E_monitor`、`A_right34`：只要 night（`backdrops_on("night")` 打开窗外背景板）。
2. **人物层**：每个片段 × 机位，场景、光照和背景完全相同，只渲人物所在的裁剪框（`use_border + use_crop_to_border`，裁剪框按每帧人物关键点 + 帽子 + 斗篷尖 + 影子落点，留 48 px，参考 `render_island.py`）。
   - 清单里 `props` 列出的道具在这个片段里**会动**，必须归人物层：`chair`（椅子，`cab_chair*` / `CHAIR_ROOT`）、`hat`（`cab_hat_*`）、`curtain_l2`（`cab_win_l2_cur_closed_*`）、`fx`（`FX_B6_<机位>` 集合：身边星光、眼里星星、脸颊红晕、只照人物的暖光）。这些道具在对应背景里要藏掉。
3. **遮罩**：Workbench，人物 + 本片段的 `props` 为白，其余黑。**B6 的星光在人物轮廓外面，遮罩必须把 `FX_B6_<机位>` 算进去**，否则会被裁掉。
4. **合成**（参考 `compose_island.py`）：有人物 ÷ 背景（第 ((f−1) mod 192)+1 帧）= 阴影比例；变暗 < 0.05 当噪点；开运算去细线；裁剪边缘 16 px 渐隐。清单里 `fade_in` / `fade_out` > 0 的片段在开头 / 结尾做 12 帧透明度淡入 / 淡出（上床、起床、进出门都是转场，不做动画）。

**输出**（放 `D:\gsd_cabin\output\video\`，不进 Git）：
- `bg_cabin_<变体>.mp4`（主镜头）、`bg_cabin_night_<机位>.mp4`（书桌机位），H.264；
- `<片段>.webm` 或 `<片段>_<机位>.webm`（VP9 + 透明，文件名按清单 `files`），外加 `preview_<片段>…mp4`（叠在背景上的预览）；
- `clips_cabin.json`：在构建生成的清单基础上，每个片段补 `x / y / w / h`（人物层在 2560×1440 画面里的位置）、`background` 文件名；格式同岛屿 `clips_<时段>.json`（`交接文档_claude.md` 第 10 节），多出来的 `trigger`（B6 = `task_done`）、`next`、`fade_in`、`fade_out`、`cams` 字段保留。

### 4. 步骤和汇报
1. 先每个片段 × 机位各渲 **1 帧**（人物层 + 遮罩 + 合成）、每个背景变体 1 帧，报告每帧耗时和截图，等用户确认。
2. 用户确认后全量渲染 + 合成；支持断点续渲（已存在的帧跳过）。
3. 成品检查报告 `docs/04_Harness/木屋室内成品检查.md`：每段抽 3–5 帧，看有没有方框、闪烁暗斑、假阴影、星光被裁、道具在背景里重复出现 / 缺失、淡入淡出是否正确；缩小的检查图放 `evidence/cabin_interior/final_v1/`。
4. 只提交脚本、文档、缩小的检查图到 `feat/cabin-interior`；提交信息格式 `<类型>(<范围>): <说明>`，例如 `feat(cabin): 室内三层渲染与合成脚本`。

### 用户定下的规则（不能改）
- 夜里学习（night）和深夜睡觉（late）**屋里灯具全关，光都来自显示器**：窄光束照她的脸、深夜一盏余光照床，再加一盏照全屋的暖色点光 `L_monitor_room`（电脑周围最亮、远端变暗）；深夜三盏一起微弱闪烁（192 帧整周期）。月光和天空环境光保留（`TIME_CFG` 的 power 0.6 / wpow 0.2，不要改成 0）。
- **B6 的星光、眼里星星、红晕只在 B6 里出现**；其它片段画面里不能有（`fx_on(None, False)`）。
- B6 在用户完成任务时播放：B1 → B6 → 回 B1，首尾 = B1 第 1 帧。
- 上床、起床、出门都用淡入淡出转场。
- G5 是魔法戴帽（帽子自己飘到头上），没有任何光效。
- 室内人物不加描边。

### 硬约束
- Blender 5.2，一律无界面运行；不要用低版本保存 .blend。
- 2560×1440，24 fps；循环 192 帧（第 193 帧 = 第 1 帧）；环境动画必须 192 帧整周期。
- 改材质颜色先做 sRGB → 线性（`lin()`）。
- 人物模型有版权（只用于非商业课程演示）：.blend、人物贴图、渲染成品都不进 Git、不公开发布；仓库里只放脚本、文档和缩小的检查图。
- 灯光可以微调（深夜主镜头偏暗可以提一点），但要守上面的规则；改了哪些 `TIME_CFG` 参数写进检查报告，由 Claude 合回脚本。

### 已知问题（不用你修，看到时记一笔）
- B6 双手是手指伸直的合掌，不是十指交扣；显示器后机位手指会挡一点脸颊边。
- W_desk_bed 有几帧斗篷和长袍毫米级的细小穿插（还没做真正的布料碰撞）。
- A4_up 是 A4_sit 倒放。
