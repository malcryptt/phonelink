@echo off
echo [*] Installing PhoneLink Windows Background Daemon...

SET STARTUP_DIR="%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
SET VBS_PATH="%STARTUP_DIR%\phonelink_daemon.vbs"

:: Create the silent VBS launcher
echo Set WshShell = CreateObject("WScript.Shell") > %VBS_PATH%
echo WshShell.Run "cmd /c phonelink web", 0, False >> %VBS_PATH%

echo [ok] Daemon installed to Windows Startup folder.
echo [ok] The server will now silently start in the background every time you log in.
echo.
echo Would you like to start the daemon right now?
pause
cscript //nologo %VBS_PATH%
echo [ok] PhoneLink is currently active on port 8000!
