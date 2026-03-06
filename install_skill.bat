@echo off
setlocal enabledelayedexpansion

echo Installing context-probe skill...
echo.
echo Choose installation location:
echo   1) Current project (.claude\skills\)
echo   2) User home (%%USERPROFILE%%\.claude\skills\)
echo   3) Custom path
echo.

set /p choice="Enter choice [1-3]: "

if "%choice%"=="1" (
    set "SKILL_DIR=.claude\skills\context-probe"
) else if "%choice%"=="2" (
    set "SKILL_DIR=%USERPROFILE%\.claude\skills\context-probe"
) else if "%choice%"=="3" (
    set /p custom_path="Enter custom path: "
    set "SKILL_DIR=!custom_path!\context-probe"
) else (
    echo Invalid choice. Installation cancelled.
    exit /b 1
)

set "SOURCE_DIR=."
set "SOURCE_FILE=SKILL.md"
set "TARGET_FILE=%SKILL_DIR%\SKILL.md"

REM Extract source version
for /f "tokens=2" %%v in ('findstr /b "version:" "%SOURCE_FILE%"') do set "SOURCE_VERSION=%%v"

REM Check if already installed
if exist "%TARGET_FILE%" (
    for /f "tokens=2" %%v in ('findstr /b "version:" "%TARGET_FILE%"') do set "TARGET_VERSION=%%v"
    echo.
    echo Skill already installed at: %SKILL_DIR%
    echo Installed version: !TARGET_VERSION!
    echo New version: %SOURCE_VERSION%
    echo.
    set /p overwrite="Overwrite existing skill? [y/N]: "
    if /i not "!overwrite!"=="y" (
        echo Installation cancelled
        exit /b 0
    )
)

REM Create directory and install
if not exist "%SKILL_DIR%" mkdir "%SKILL_DIR%"
copy /y SKILL.md "%SKILL_DIR%\" >nul
copy /y context_probe.py "%SKILL_DIR%\" >nul
copy /y context_config.jsonc.template "%SKILL_DIR%\" >nul

echo.
echo [32m✓[0m Skill installed to: %SKILL_DIR%
echo   Version: %SOURCE_VERSION%
echo.
echo You can now use it by asking Claude to test context windows

endlocal
