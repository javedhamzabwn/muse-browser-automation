' Muse Browser MCP autostart (generic — no hardcoded usernames or paths).
' install.ps1 copies this file into the user's Startup folder.
' Starts the loopback daemon hidden at login: pythonw.exe must be on PATH
' (install.ps1 ensures this) and the repo must be deployed to
' %USERPROFILE%\muse-browser-mcp\.
Set WshShell = CreateObject("WScript.Shell")
DaemonPath = WshShell.ExpandEnvironmentStrings("%USERPROFILE%") & "\muse-browser-mcp\daemon\simpled.py"
WshShell.Run """pythonw.exe"" """ & DaemonPath & """", 0, False
