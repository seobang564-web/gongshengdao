@echo off
cd /d "%~dp0"
call "%~dp0_find_blender.bat" || exit /b
echo === Test: 1 final-quality frame of every clip, for night / morning / noon ===
for %%T in (night morning noon) do "%BL%" -b island_%%T.blend -P scripts\render_island.py -- test
echo.
echo Done. Time estimates are at the end of output\render_log_night.txt / _morning.txt / _noon.txt
echo Check images in output\bg_night\ and output\raw\
pause
