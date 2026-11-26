# 给 Windows Codex 的提示词 · 木屋室内灯光调色（2026-11-25）

> 用法：在 Windows 上把仓库切到 `feat/cabin-interior` 分支，把下面「提示词」整段发给 Codex。
> 场景 .blend 不进 Git，由用户把 `cabin_whitebox.blend`（Mac 上运行脚本后生成，贴图需先打包）拷到 Windows，例如 `D:\gsd_cabin\cabin_whitebox.blend`。

---

## 提示词

你在做大学生桌面日程应用「共生岛」的美术部分。仓库：`gongshengdao`，分支 `feat/cabin-interior`。先读：
- `docs/04_Harness/木屋室内交接.md`（这次的场景）
- `docs/04_Harness/交接文档_claude.md`（项目总览，第 3 节硬约束、第 5.4 节渲染与合成原理）
- `blender/cabin_interior/cabin_whitebox.py`（场景脚本；时段参数在 `TIME_CFG`，窗帘在 `CURTAIN`，函数 `apply_time()`）
- 参考成品：岛屿 `blender/island_final/scripts/render_island.py`

**分工**：几何、布局、人物姿势和动画由 Mac 上的 Claude 负责，你**不要改模型、家具位置、人物姿势、被子形状**。你负责灯光调色、EEVEE 渲染设置、之后的渲染与合成、成品检查。

**这次的任务：四个时段的灯光调色**
1. 用 Blender 5.2 无界面打开 `D:\gsd_cabin\cabin_whitebox.blend`（`blender -b ... -P 你的脚本.py`）。脚本里调用 `apply_time(t)` 的逻辑已经在 .blend 里烘好了一种状态，你需要在自己的脚本里按 `cabin_whitebox.py` 的 `TIME_CFG` 和 `set_state()` 切换时段，或者只调灯光参数。
2. 目标：和岛屿同一套画风（风格化 PBR、AgX + Punchy、柔和泛光），室内要温暖、干净、精致：
   - `night`：书桌学习，台灯和火炉是主光，暖色；窗外蓝调月光，室内不要死黑。
   - `day`：明亮自然光从北窗和东窗进来，阴影柔和，不要过曝。
   - `dawn`：窗帘拉上，东窗 `win_l1` 留缝，一道晨光斜照在床上 / 被子上，其余偏冷偏暗。
   - `late`：深夜睡觉，只有床头小夜灯和一点月光，能看清人物的脸。
3. 先每个时段试 1 帧（2560×1440），报告每帧耗时和截图，用户确认后再做别的。
4. 交付：一份 `docs/04_Harness/室内调色结果.md`，写清每个时段改了哪些参数（太阳方向 / 强度 / 颜色、世界光、各灯光强度和颜色、曝光、泛光），用 `TIME_CFG` 同样的键名，方便 Claude 合回脚本；外加四张对比图放 `evidence/cabin_interior/lookdev_v1/`。提交到 `feat/cabin-interior`，提交信息格式 `<类型>(<范围>): <说明>`，例如 `style(cabin): 四个时段灯光调色`。

**硬约束**
- Blender 5.2；不要用低版本保存 .blend。
- 改材质颜色先做 sRGB → 线性转换（脚本里的 `lin()`）。
- 室内人物**不加任何描边**。
- 环境动画（火焰、灯光闪烁）必须是 192 帧整周期（Cyclic 或整数频率正弦），不能用不周期的噪声。
- 人物模型有版权：.blend、人物贴图、渲染结果都不进 Git、不公开发布；仓库里只放脚本、文档和缩小的检查图。
- 不改 `cabin_whitebox.py` 的几何和人物部分；需要改的地方写在结果文档里，由 Claude 处理。
