@echo off
set "BL=C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
if exist "%BL%" exit /b 0
for /d %%D in ("C:\Program Files\Blender Foundation\Blender 5.*") do if exist "%%D\blender.exe" set "BL=%%D\blender.exe"
if exist "%BL%" exit /b 0
echo Blender 5.2 not found. Open _find_blender.bat with Notepad and set BL to your blender.exe path.
pause
exit /b 1
