@echo off
cd /d "%~dp0"
call "%~dp0_find_blender.bat" || exit /b
for %%T in (night morning noon) do "%BL%" -b -P scripts\compose_island.py -- %%T
pause
