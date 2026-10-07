@echo off
echo =======================================
echo       Starting Muse MCP Stack
echo =======================================
echo.
echo Launching Gateway and all associated Browser Engines...
echo (Obscura, Camoufox, Moli, Playwright)
echo.

cd /d "%~dp0"
python cli.py start

pause
