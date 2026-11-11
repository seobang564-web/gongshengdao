@echo off
cd /d "%~dp0"
call "%~dp0_find_blender.bat" || exit /b
echo === Render morning: background loop + character clips + masks (resumable) ===
"%BL%" -b island_morning.blend -P scripts\render_island.py -- all
echo === Compose morning: transparent character layers + videos ===
"%BL%" -b -P scripts\compose_island.py -- morning
echo Done. Results in output\video\
pause
