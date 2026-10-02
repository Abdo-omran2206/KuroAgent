@echo off
title KURO 2.0 Inno Setup Installer Builder
echo ============================================================
echo   KURO 2.0 Inno Setup Windows Installer Builder
echo ============================================================
echo.

set ISCC_PATH=

:: Check PATH first
where ISCC.exe >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set ISCC_PATH=ISCC.exe
    goto FOUND
)

:: Check standard Inno Setup installation paths
if exist "C:\Program Files\Inno Setup 7\ISCC.exe" set ISCC_PATH="C:\Program Files\Inno Setup 7\ISCC.exe"
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC_PATH="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set ISCC_PATH="C:\Program Files\Inno Setup 6\ISCC.exe"

:FOUND
if "%ISCC_PATH%"=="" (
    echo [Error] Inno Setup Compiler (ISCC.exe) not found.
    echo Please install Inno Setup from https://jrsoftware.org/isinfo.php
    echo.
    pause
    exit /b 1
)

echo [Notice] Using Inno Setup Compiler: %ISCC_PATH%
echo [Build] Compiling build\setup_installer.iss...
echo.

%ISCC_PATH% build\setup_installer.iss

echo.
if %ERRORLEVEL% EQU 0 (
    echo ============================================================
    echo   INSTALLER BUILD SUCCESSFUL! 
    echo   Setup Installer Location: dist\KURO_v2_Setup.exe
    echo ============================================================
) else (
    echo ============================================================
    echo   INSTALLER BUILD FAILED! Check error messages above.
    echo ============================================================
)
echo.
pause
