@echo off
cd /d "%~dp0"
call "%~dp0_find_blender.bat" || exit /b
"%BL%" -b -P scripts\compose_classroom.py -- classroom
pause
