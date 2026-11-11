@echo off
cd /d "%~dp0"
call "%~dp0_find_blender.bat" || exit /b
echo === Render night: background loop + character clips + masks (resumable) ===
"%BL%" -b island_night.blend -P scripts\render_island.py -- all
echo === Compose night: transparent character layers + videos ===
"%BL%" -b -P scripts\compose_island.py -- night
echo Done. Results in output\video\
pause
