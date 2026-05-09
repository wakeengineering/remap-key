Option Explicit

Dim fso, shell, scriptDir, parentDir, scriptFile, logFile, pythonExe, candidates, i, cmdLine
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
parentDir = fso.GetParentFolderName(scriptDir)
scriptFile = fso.BuildPath(scriptDir, "remap-key.py")
Dim configFile
configFile = fso.BuildPath(scriptDir, "remap-key.config.json")
logFile = fso.BuildPath(scriptDir, "remap-key.task.log")

candidates = Array( _
    fso.BuildPath(scriptDir, "python.venv-remap\Scripts\python.exe"), _
    fso.BuildPath(scriptDir, ".venv-remap\Scripts\python.exe"), _
    fso.BuildPath(parentDir, "python.venv-remap\Scripts\python.exe"), _
    fso.BuildPath(parentDir, ".venv-remap\Scripts\python.exe"), _
    fso.BuildPath(scriptDir, "python.venv-remap\Scripts\pythonw.exe"), _
    fso.BuildPath(scriptDir, ".venv-remap\Scripts\pythonw.exe"), _
    fso.BuildPath(parentDir, "python.venv-remap\Scripts\pythonw.exe"), _
    fso.BuildPath(parentDir, ".venv-remap\Scripts\pythonw.exe") _
)

pythonExe = ""
For i = 0 To UBound(candidates)
    If fso.FileExists(candidates(i)) Then
        pythonExe = candidates(i)
        Exit For
    End If
Next

If pythonExe = "" Then
    AppendLog logFile, "Could not find python executable in expected virtual-environment paths."
    WScript.Quit 1
End If

If Not fso.FileExists(scriptFile) Then
    AppendLog logFile, "Missing script: " & scriptFile
    WScript.Quit 1
End If

If Not fso.FileExists(configFile) Then
    AppendLog logFile, "Missing config: " & configFile
    WScript.Quit 1
End If

AppendLog logFile, "Launcher started. Using Python: " & pythonExe
AppendLog logFile, "Launching remapper in hidden mode."
cmdLine = Quote(pythonExe) & " " & Quote(scriptFile) & " --config " & Quote(configFile) & " --log-file " & Quote(logFile)
shell.CurrentDirectory = scriptDir
shell.Run cmdLine, 0, False
WScript.Quit 0

Sub AppendLog(path, message)
    Dim ts
    Set ts = fso.OpenTextFile(path, 8, True)
    ts.WriteLine "[" & Now & "] " & message
    ts.Close
End Sub

Function Quote(s)
    Quote = Chr(34) & s & Chr(34)
End Function
