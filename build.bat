@echo off
title KURO 2.0 Standalone Builder
echo ============================================================
echo   KURO 2.0 Standalone Executable Builder
echo ============================================================
echo.

python build/build_exe.py

echo.
if %ERRORLEVEL% EQU 0 (
    echo ============================================================
    echo   BUILD SUCCESSFUL! Executable created: dist\KURO.exe
    echo ============================================================
) else (
    echo ============================================================
    echo   BUILD FAILED! Check error output above.
    echo ============================================================
)
echo.
pause
