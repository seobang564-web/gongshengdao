#!/bin/bash
# 窗外岛屿背景板：早 / 午 / 夜三个时段 × 正面 / 西侧两个方向（Mac 上约 4 分钟）
BL=/Applications/Blender.app/Contents/MacOS/Blender
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HOME/Desktop/共生岛/blender/island_final"
for t in night morning noon; do
  "$BL" -b "$SRC/island_$t.blend" -P "$HERE/render_window_bg.py" -- --tag "$t" --pct 100 --samples 64 --views front,west
done
