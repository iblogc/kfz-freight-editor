@echo off
echo Building Windows executable using Nuitka...
python scripts/build_nuitka.py
if %ERRORLEVEL% NEQ 0 (
    echo Build failed!
    pause
    exit /b %ERRORLEVEL%
)
echo Build successful!
pause
