' Background start for packaged app: place next to Worklog.exe OR run from project after build.
' Double-click this file after packaging, or copy into dist\Worklog\
Option Explicit
Dim sh, fso, here, exePath, port
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

here = fso.GetParentFolderName(WScript.ScriptFullName) & "\"
exePath = here & "Worklog.exe"
If Not fso.FileExists(exePath) Then
  exePath = here & "dist\Worklog\Worklog.exe"
End If
If Not fso.FileExists(exePath) Then
  MsgBox "Worklog.exe not found." & vbCrLf & "Put this VBS next to Worklog.exe, or build first.", vbCritical, "Worklog"
  WScript.Quit 1
End If

' WindowStyle 0 = hide console
sh.CurrentDirectory = fso.GetParentFolderName(exePath)
sh.Run """" & exePath & """", 0, False

WScript.Sleep 2000
sh.Run "http://127.0.0.1:8501", 1, False
