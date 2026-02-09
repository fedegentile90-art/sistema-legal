Option Explicit

Dim fso, shellObj, scriptDir, ps1Path, cmd

Set fso = CreateObject("Scripting.FileSystemObject")
Set shellObj = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
ps1Path = scriptDir & "\RUN_ERP.ps1"

cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & ps1Path & """"
shellObj.Run cmd, 0, False
