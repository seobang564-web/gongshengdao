@echo off
cd /d "%~dp0"
call "%~dp0_find_blender.bat" || exit /b
echo === Render noon: background loop + character clips + masks (resumable) ===
"%BL%" -b island_noon.blend -P scripts\render_island.py -- all
echo === Compose noon: transparent character layers + videos ===
"%BL%" -b -P scripts\compose_island.py -- noon
echo Done. Results in output\video\
pause
