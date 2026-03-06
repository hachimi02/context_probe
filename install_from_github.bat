@echo off
REM Install context-probe skill from GitHub

setlocal enabledelayedexpansion

set "REPO=hachimi02/context_probe"
set "VERSION=%~1"
if "%VERSION%"=="" set "VERSION=main"
set "BASE_URL=https://raw.githubusercontent.com/%REPO%/%VERSION%"

echo Installing context-probe skill from GitHub...
echo Version: %VERSION%
echo.
echo Choose installation location:
echo   1) Current project (.claude\skills\)
echo   2) User home (%USERPROFILE%\.claude\skills\)
echo   3) Custom path
echo.
set /p "choice=Enter choice [1-3]: "

if "%choice%"=="1" (
    set "SKILL_DIR=.claude\skills\context-probe"
) else if "%choice%"=="2" (
    set "SKILL_DIR=%USERPROFILE%\.claude\skills\context-probe"
) else if "%choice%"=="3" (
    set /p "CUSTOM_PATH=Enter custom path: "
    set "SKILL_DIR=!CUSTOM_PATH!\context-probe"
) else (
    echo Invalid choice. Installation cancelled.
    exit /b 1
)

REM Create directory
if not exist "%SKILL_DIR%" mkdir "%SKILL_DIR%"

REM Download files
echo.
echo Downloading files...

set "FILES=SKILL.md context_probe.py context_config.jsonc.template"
for %%f in (%FILES%) do (
    echo   - %%f
    curl -fsSL "%BASE_URL%/%%f" -o "%SKILL_DIR%\%%f"
    if errorlevel 1 (
        echo Error downloading %%f
        exit /b 1
    )
)

echo.
echo [32m✓[0m Skill installed to: %SKILL_DIR%
echo.
echo Usage: Type '/context-probe' in your AI client
