' Hidden background start for source-code mode
' Args: [0]=project root, [1]=port
Option Explicit
Dim sh, root, port, py, cmd, fso, logPath
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

If WScript.Arguments.Count >= 1 Then
  root = WScript.Arguments(0)
Else
  root = fso.GetParentFolderName(WScript.ScriptFullName) & "\"
End If
If WScript.Arguments.Count >= 2 Then
  port = WScript.Arguments(1)
Else
  port = "8501"
End If

If Right(root, 1) <> "\" Then root = root & "\"
py = root & ".venv\Scripts\python.exe"
If Not fso.FileExists(py) Then
  WScript.Echo "python not found: " & py
  WScript.Quit 1
End If

logPath = root & "streamlit.log"
' 0 = hidden window, False = do not wait
cmd = """" & py & """ -m streamlit run """ & root & "app.py"" --server.headless true --server.port " & port & " --server.address 127.0.0.1"
sh.CurrentDirectory = root
sh.Run "cmd /c " & cmd & " > """ & logPath & """ 2>&1", 0, False
WScript.Quit 0
