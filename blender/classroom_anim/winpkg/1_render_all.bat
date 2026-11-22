@echo off
cd /d "%~dp0"
call "%~dp0_find_blender.bat" || exit /b
echo === Render classroom: background loop + Elaina + teacher clips + masks (resumable) ===
"%BL%" -b classroom.blend -P scripts\render_classroom.py -- all
echo === Compose: transparent character layers + videos ===
"%BL%" -b -P scripts\compose_classroom.py -- classroom
echo Done. Results in output\video\
pause
