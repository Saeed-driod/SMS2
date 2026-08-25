@echo off
cd /d "%~dp0"
title School Management ^& Fee Voucher Studio - Alliedian School Okara
color 0B
cls

echo =====================================================================
echo    ALLIEDIAN SCHOOL AL-REHMAN CAMPUS - FEE MANAGEMENT ^& VOUCHER STUDIO
echo =====================================================================
echo.
echo  Initializing application system...
echo.

:: Check and activate virtual environment
set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
)

:: Check Python installation
%PYTHON_EXE% --version >nul 2>&1
if %errorlevel% neq 0 (
    color 0C
    echo [ERROR] Python is not installed or not added to your system PATH!
    echo Please install Python 3.8+ before running this application.
    echo.
    pause
    exit
)

:: Validate packages and install missing ones
echo  Checking Python library dependencies...
%PYTHON_EXE% -c "import flask, openpyxl, pandas, jinja2" >nul 2>&1
if %errorlevel% neq 0 (
    echo  Installing missing libraries ^(flask, openpyxl, pandas, werkzeug^)...
    if exist ".venv\Scripts\pip.exe" (
        .venv\Scripts\pip.exe install -r requirements.txt
    ) else (
        pip install -r requirements.txt
    )
    if %errorlevel% neq 0 (
        color 0C
        echo [ERROR] Failed to install required Python libraries.
        echo Please ensure you are connected to the internet and try again.
        echo.
        pause
        exit
    )
)

echo  Dependencies verified successfully!
echo.
echo  Starting local web server in the background...
echo  Please keep this window open while using the Studio.
echo.

:: Launch Flask app in a separate background process
start "School Management Studio Server" /Min %PYTHON_EXE% app.py

:: Wait for Flask to boot up
echo  Waiting for server to start...
timeout /t 3 /nobreak >nul

:: Open default browser to localhost
echo  Opening Fee Studio in your default browser...
start http://localhost:3013

echo.
echo =====================================================================
echo  STUDIO RUNNING SUCCESSFULLY!
echo  URL: http://localhost:3013
echo =====================================================================
echo.
echo  [TO STOP THE STUDIO]
echo  Press any key in this window to shut down the server.
echo.
pause

:: Terminate Python background process on exit
echo  Stopping local server...
taskkill /FI "WINDOWTITLE eq School Management Studio Server*" /T /F >nul 2>&1
echo  Shutdown complete. Goodbye!
timeout /t 2 >nul
exit
