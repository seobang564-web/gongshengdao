@echo off
cd /d "%~dp0"
call "%~dp0_find_blender.bat" || exit /b
echo === Test: 1 final-quality frame of the background and every clip (classroom) ===
"%BL%" -b classroom.blend -P scripts\render_classroom.py -- test
echo.
echo Done. Time estimate is at the end of output\render_log_classroom.txt
echo Check images in output\bg_classroom\ and output\raw\
pause
