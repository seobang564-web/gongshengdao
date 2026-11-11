# 共生岛：课表驱动的大学生桌面日程与 AI 人物陪伴应用

课程项目（中期）。桌面日程应用：课表导入 → 今日待办排程 → 虚拟人物 AI 聊天；桌面呈现为一座会随时间变化的岛屿，人物伊蕾娜在岛上按日程活动。

## 当前进度（2026-11-11 中期）
| 部分 | 状态 |
|---|---|
| 需求、规约、ADR、Harness、计划与任务分解 | ✅ 见 `docs/` |
| 美术管线：岛屿场景 v4（早/午/夜三套光照）、魔法教室场景 | ✅ 脚本化生成，见 `blender/` |
| 人物：导入与骨骼修复、站立待机循环、Mixamo 动作重定向、斗篷物理摆动 | ✅ |
| 岛屿最终版：15 个人物片段 + 背景循环的构建、渲染、合成流水线 | ✅ 已在 Mac 上端到端验证，Windows 正式渲染中 |
| 课表识别、排程算法、AI 聊天、桌面窗口 | ⬜ 下一阶段（见 `docs/05_Global_Plan_Tasks/Plan.md`） |

## 目录
```
docs/
  01_需求/            需求说明（整理自开题报告）
  02_规约/            验收规约：最终验收逐条检查的标准（编号、测试方法、通过标准、证据）
  03_ADR/             前置调研（需求 / 规约 / 技术）+ 架构决策记录
  04_Harness/         项目级 Harness：开发规范、AI 操作约定、代码规范、文档规范、日志规范、观测性约定
  05_Global_Plan_Tasks/  项目级目标（Global）、初期计划（Plan）、任务分解规范与任务表（Tasks）
blender/              Blender 5.2 脚本（全部无界面运行：blender -b ... -P 脚本）
  gongshengdao_scene_v3.py / _v4.py   岛屿场景
  import_character.py / animate_loop.py   人物导入与待机循环
  retarget_mixamo.py / cloth_sim.py       动作重定向、斗篷物理
  magic_classroom.py + classroom_parts/   魔法教室场景
  island_final/       岛屿最终版：片段构建 build_clips.py、渲染 scripts/render_island.py、合成 scripts/compose_island.py、Windows 批处理 winpkg/
evidence/             评测证据：构建日志、闭合检查、渲染与合成日志、检查图
```

## 运行（需要 Blender 5.2）
```bash
# 1. 生成动画工程（场景 + 人物 + 待机循环）
blender -b -P blender/build_anim_v4.py
# 2. 构建岛屿全部人物片段 → island_{morning,noon,night}.blend
blender -b blender/gongshengdao_v4_anim.blend -P blender/island_final/build_clips.py
# 3. 渲染与合成（Windows 上用 winpkg/*.bat）
blender -b island_night.blend -P scripts/render_island.py -- all
blender -b -P scripts/compose_island.py -- night
```

## 不在仓库里的文件
- 人物模型（`blender/characters/`）：伊蕾娜出自《魔女之旅》（白石定规 / SB Creative），仅用于非商业课程演示，不随仓库分发。
- Mixamo 动作 FBX（`动作/`）：从 mixamo.com 下载，文件名见 `docs/04_Harness/开发规范.md`。
- .blend、渲染帧、视频、压缩包：体积大，由脚本生成。
