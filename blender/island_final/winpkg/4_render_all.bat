@echo off
cd /d "%~dp0"
call "%~dp0_find_blender.bat" || exit /b
for %%T in (night morning noon) do (
  echo === Render %%T ===
  "%BL%" -b island_%%T.blend -P scripts\render_island.py -- all
  echo === Compose %%T ===
  "%BL%" -b -P scripts\compose_island.py -- %%T
)
echo All done. Results in output\video\
pause
