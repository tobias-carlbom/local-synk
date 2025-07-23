@echo off
setlocal

:: Set service name
set SERVICE_NAME=local-synk

:: Get current directory
set CURRENT_DIR=%~dp0

:: Set paths
set NSSM_PATH=%CURRENT_DIR%nssm.exe

echo Uninstalling local-synk Windows Service...
echo.

:: Check if NSSM exists
if not exist "%NSSM_PATH%" (
    echo ERROR: nssm.exe not found at %NSSM_PATH%
    echo Please ensure nssm.exe is in the same directory as this script.
    pause
    exit /b 1
)

:: Check if service exists
echo Checking if service exists...
"%NSSM_PATH%" status "%SERVICE_NAME%" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Service "%SERVICE_NAME%" is not installed.
    echo Nothing to uninstall.
    pause
    exit /b 0
)

:: Stop the service
echo Stopping service...
"%NSSM_PATH%" stop "%SERVICE_NAME%" >nul 2>&1

:: Wait a moment for service to stop
echo Waiting for service to stop...
timeout /t 5 /nobreak >nul

:: Remove the service
echo Removing service...
"%NSSM_PATH%" remove "%SERVICE_NAME%" confirm

if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to remove service.
    echo You may need to run this script as Administrator.
    pause
    exit /b 1
)

echo.
echo Service uninstalled successfully!
echo Service Name: %SERVICE_NAME%
echo.
echo The service has been completely removed from the system.
echo You can now safely delete the application files if desired.
echo.
pause
