@echo off
REM ============================================================
REM Chrome CDP 启动脚本（供 Rufus 自动模式使用）
REM ------------------------------------------------------------
REM 功能：关掉当前所有 Chrome，重开一个开了 9222 调试端口的实例，
REM       并沿用你真实登录的 Chrome profile（Default）。
REM
REM 必要前提：
REM   1) Amazon 已在这个 Chrome profile 里登录过
REM   2) 所有 Chrome 窗口都要先关（否则新进程不能附加到同 profile）
REM
REM 用法：双击即可。想用别的 profile 改 --profile-directory 参数。
REM ============================================================

setlocal enabledelayedexpansion
chcp 65001 >nul

set PORT=9222
set PROFILE_DIR=Default

echo.
echo ============================================================
echo   Starting Chrome with CDP debugging on port %PORT%
echo   Profile: %PROFILE_DIR% (your real login session)
echo ============================================================
echo.

REM 定位 Chrome
set CHROME=
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe

if "%CHROME%"=="" (
    echo [ERROR] Chrome not found. Install it or edit this script.
    pause
    exit /b 1
)

echo Chrome found at: %CHROME%
echo.

REM 关掉现有 Chrome（必须关干净，不然新进程起不了调试端口）
echo Closing existing Chrome processes...
taskkill /F /IM chrome.exe /T >nul 2>&1
timeout /t 2 /nobreak >nul

REM 启动带调试端口的 Chrome，复用真实 profile
echo Launching Chrome with debugging port %PORT%...
start "" "%CHROME%" ^
  --remote-debugging-port=%PORT% ^
  --remote-allow-origins=* ^
  --profile-directory="%PROFILE_DIR%" ^
  --no-first-run ^
  --no-default-browser-check ^
  https://www.amazon.com/

echo.
echo ============================================================
echo   Chrome launched.
echo   - Verify: http://127.0.0.1:%PORT%/json/version
echo   - In the app: click "Test Chrome" in Rufus panel
echo ============================================================
echo.
echo You can close this window.
timeout /t 5 /nobreak >nul
