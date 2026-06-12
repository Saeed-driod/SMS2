@echo off
title School Management & Fee Voucher Studio - Allied School Okara
color 0B
cls

echo =====================================================================
echo    ALLIED SCHOOL AL-REHMAN CAMPUS - FEE MANAGEMENT & VOUCHER STUDIO
echo =====================================================================
echo.
echo  Initializing application system...
echo.

:: Check Python installation
python --version >nul 2>&1
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
python -c "import flask, openpyxl, pandas, jinja2" >nul 2>&1
if %errorlevel% neq 0 (
    echo  Installing missing libraries (flask, openpyxl, pandas)...
    pip install flask openpyxl pandas
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
start "School Management Studio Server" /Min python app.py

:: Wait for Flask to boot up
echo  Waiting for server to start...
timeout /t 3 /nobreak >nul

:: Open default browser to localhost
echo  Opening Fee Studio in your default browser...
start http://localhost:5000

echo.
echo =====================================================================
echo  STUDIO RUNNING SUCCESSFULLY!
echo  URL: http://localhost:5000
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
