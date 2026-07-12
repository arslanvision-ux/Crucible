@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo Crucible VFX Toolkit - Nuke Installer
echo ===================================================
echo.

set "NUKE_DIR=%USERPROFILE%\.nuke"
set "DEST_DIR=%NUKE_DIR%\Crucible"
set "SRC_DIR=%~dp0Crucible"
set "INIT_FILE=%NUKE_DIR%\init.py"
set "PLUGIN_LINE=nuke.pluginAddPath('%NUKE_DIR:\=/%/Crucible')"

echo Please select an option:
echo [1] Install Crucible
echo [2] Uninstall Crucible
echo [3] Cancel
echo.
set /p CHOICE="Enter your choice (1-3): "

if "%CHOICE%"=="1" goto install
if "%CHOICE%"=="2" goto uninstall
goto end

:install
if not exist "%SRC_DIR%" (
    echo [ERROR] Could not find the Crucible folder next to this installer.
    echo Please make sure this .bat file is running from the extracted folder.
    pause
    exit /b 1
)

echo [INFO] Target .nuke directory: %NUKE_DIR%

:: Create .nuke if it doesn't exist (rare, but possible)
if not exist "%NUKE_DIR%" (
    echo [INFO] Creating .nuke directory...
    mkdir "%NUKE_DIR%"
)

:: Copy Crucible folder
echo [INFO] Copying Crucible files to %DEST_DIR%...
if exist "%DEST_DIR%" (
    echo [INFO] Removing old Crucible installation...
    rmdir /s /q "%DEST_DIR%"
)
xcopy /e /i /q /y "%SRC_DIR%" "%DEST_DIR%"

echo [INFO] Updating init.py...
if not exist "%INIT_FILE%" (
    echo !PLUGIN_LINE!> "%INIT_FILE%"
    echo [SUCCESS] Created new init.py and added Crucible path.
) else (
    findstr /c:"!PLUGIN_LINE!" "%INIT_FILE%" >nul
    if errorlevel 1 (
        echo.>> "%INIT_FILE%"
        echo !PLUGIN_LINE!>> "%INIT_FILE%"
        echo [SUCCESS] Added Crucible path to existing init.py.
    ) else (
        echo [INFO] Crucible path already exists in init.py.
    )
)

echo.
echo ===================================================
echo INSTALLATION COMPLETE!
echo You can now launch Nuke. Crucible will be available
echo in the Pane menu and the top Nuke shelf menu.
echo ===================================================
pause
goto end

:uninstall
echo [INFO] Uninstalling Crucible from %NUKE_DIR%...
if exist "%DEST_DIR%" (
    echo [INFO] Removing Crucible folder...
    rmdir /s /q "%DEST_DIR%"
    echo [SUCCESS] Crucible folder removed.
) else (
    echo [INFO] Crucible folder not found.
)

if exist "%INIT_FILE%" (
    echo [INFO] Removing Crucible path from init.py...
    findstr /v /l /c:"!PLUGIN_LINE!" "%INIT_FILE%" > "%INIT_FILE%.tmp"
    move /y "%INIT_FILE%.tmp" "%INIT_FILE%" >nul
    echo [SUCCESS] Removed Crucible path from init.py.
)

echo.
echo ===================================================
echo UNINSTALLATION COMPLETE!
echo Crucible has been removed from Nuke.
echo ===================================================
pause
goto end

:end
