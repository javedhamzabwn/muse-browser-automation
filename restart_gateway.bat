@echo off
echo =======================================
echo       Restarting Muse Gateway
echo =======================================
echo.
echo Stopping and starting the gateway in mode: Both (Local + ngrok)
echo.

cd /d "%~dp0"
echo 3 | python cli.py restart

echo.
echo =======================================
echo     Gateway Restart Completed!
echo =======================================
pause
