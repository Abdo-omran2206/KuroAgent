@echo off
title KURO 2.0 Full Master Builder (Exe + Installer)
echo ============================================================
echo   KURO 2.0 Full Master Builder (PyInstaller + Inno Setup)
echo ============================================================
echo.

echo [1/2] Building Standalone PyInstaller Executable...
python build/build_exe.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ============================================================
    echo   BUILD FAILED at PyInstaller stage! Halted.
    echo ============================================================
    pause
    exit /b 1
)

echo.
echo [2/2] Building Inno Setup Windows Installer...

set ISCC_PATH=
where ISCC.exe >nul 2>&1
if %ERRORLEVEL% EQU 0 set ISCC_PATH=ISCC.exe
if exist "C:\Program Files\Inno Setup 7\ISCC.exe" set ISCC_PATH="C:\Program Files\Inno Setup 7\ISCC.exe"
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC_PATH="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set ISCC_PATH="C:\Program Files\Inno Setup 6\ISCC.exe"

if "%ISCC_PATH%"=="" (
    echo [Notice] Inno Setup ISCC.exe compiler not found. Skipping setup installer build.
    echo Standalone executable is available at: dist\KURO.exe
    echo.
    pause
    exit /b 0
)

%ISCC_PATH% build\setup_installer.iss

echo.
if %ERRORLEVEL% EQU 0 (
    echo ============================================================
    echo   MASTER BUILD COMPLETE!
    echo   1. Standalone Executable: dist\KURO.exe
    echo   2. Setup Installer:       dist\KURO_v2_Setup.exe
    echo ============================================================
) else (
    echo ============================================================
    echo   Installer compilation failed! Check logs above.
    echo ============================================================
)
echo.
pause
