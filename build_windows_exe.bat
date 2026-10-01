@echo off
setlocal
title Android Device Manager V5.3 - Windows Build

echo ==========================================
echo  Android Device Manager V5.3
echo  Windows EXE Builder
echo ==========================================
echo.

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set PYTHON=py
) else (
    where python >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        set PYTHON=python
    ) else (
        echo Python was not found.
        echo Install Python 3 from python.org and try again.
        pause
        exit /b 1
    )
)

echo Installing/updating PyInstaller...
%PYTHON% -m pip install --upgrade pyinstaller
if %ERRORLEVEL% NEQ 0 (
    echo Failed to install PyInstaller.
    pause
    exit /b 1
)

echo.
echo Building AndroidDeviceManager_V5.3.exe...
%PYTHON% -m PyInstaller --noconfirm --clean --onefile --windowed --name AndroidDeviceManager_V5.3 android_device_manager_v5_3.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo BUILD FAILED.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo BUILD COMPLETE
echo ==========================================
echo EXE:
echo dist\AndroidDeviceManager_V5.3.exe
echo.
pause
