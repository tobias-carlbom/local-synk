@echo off
echo Building local-synk executable...

REM Create deploy/windows directory if it doesn't exist
if not exist "deploy\windows" mkdir "deploy\windows"

REM Change to deploy/windows directory
cd deploy\windows

REM Clean up previous build artifacts
echo Cleaning previous build...
if exist "build" (
    rmdir /s /q "build" 2>nul
    if exist "build" echo Warning: Could not remove build folder - continuing anyway
)
if exist "dist" (
    rmdir /s /q "dist" 2>nul
    if exist "dist" echo Warning: Could not remove dist folder - continuing anyway
)
if exist "*.spec" del /q "*.spec" 2>nul

REM Build the executable
echo Building executable...
echo old command nicegui-pack --name "local-synk" ..\..\main.py

echo.
echo Building with pyinstaller directly...
pyinstaller --name "local-synk" --collect-all nicegui --hidden-import "win32api" ..\..\main.py

echo Build complete! Check deploy\windows\dist for the executable.
pause
