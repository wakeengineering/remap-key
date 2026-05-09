param(
    [string]$TaskName = "RemapKeyOnLogon",
    [switch]$RunElevated = $true,
    [switch]$StartNow,
    [switch]$LabelProcess
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $PSCommandPath
$scriptPath = Join-Path $scriptDir "remap-key.py"
$configPath = Join-Path $scriptDir "remap-key.config.json"
$logPath = Join-Path $scriptDir "remap-key.task.log"

if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "Script not found: $scriptPath"
}

$parentDir = Split-Path -Parent $scriptDir
$pythonCandidates = @(
    (Join-Path $scriptDir "python.venv-remap\Scripts\pythonw.exe"),
    (Join-Path $scriptDir ".venv-remap\Scripts\pythonw.exe"),
    (Join-Path $parentDir "python.venv-remap\Scripts\pythonw.exe"),
    (Join-Path $parentDir ".venv-remap\Scripts\pythonw.exe"),
    (Join-Path $scriptDir "python.venv-remap\Scripts\python.exe"),
    (Join-Path $scriptDir ".venv-remap\Scripts\python.exe"),
    (Join-Path $parentDir "python.venv-remap\Scripts\python.exe"),
    (Join-Path $parentDir ".venv-remap\Scripts\python.exe")
)

$pythonExe = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $pythonExe) {
    throw "Could not find python executable in expected virtual-environment paths."
}

$taskExe = $pythonExe
$labelStatus = "disabled"

# Optional: copy pythonw/python to a clearly labelled exe for Task Manager.
if ($LabelProcess) {
    $scriptsDir = Split-Path -Parent $pythonExe
    $labelledExe = Join-Path $scriptsDir "remap-key.exe"
    try {
        Copy-Item -LiteralPath $pythonExe -Destination $labelledExe -Force
        $taskExe = $labelledExe
        $labelStatus = "enabled ($labelledExe)"
    }
    catch {
        Write-Warning "Could not create/use labelled exe. Falling back to original python executable. Error: $($_.Exception.Message)"
        $taskExe = $pythonExe
        $labelStatus = "failed; using original"
    }
}

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$runLevel = if ($RunElevated) { "Highest" } else { "Limited" }

$actionArgs = "`"$scriptPath`" --config `"$configPath`" --log-file `"$logPath`""
$action = New-ScheduledTaskAction -Execute $taskExe -Argument $actionArgs -WorkingDirectory $scriptDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$principal = $null
$chosenLogonType = $null
foreach ($candidate in @("Interactive", "InteractiveToken", "InteractiveOrPassword")) {
    try {
        $principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType $candidate -RunLevel $runLevel
        $chosenLogonType = $candidate
        break
    }
    catch {
        continue
    }
}

if (-not $principal) {
    throw "Could not create a compatible scheduled task principal for user '$currentUser'."
}

$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -Hidden

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Run remap-key.py at logon for current user." `
    -Force | Out-Null

if ($StartNow) {
    Start-ScheduledTask -TaskName $TaskName
}

Write-Host "Scheduled task '$TaskName' is registered for $currentUser."
Write-Host "Run level: $runLevel"
Write-Host "Logon type: $chosenLogonType"
Write-Host "Executable: $taskExe"
Write-Host "Process label mode: $labelStatus"
Write-Host "Action args: $actionArgs"
Write-Host "Log file: $logPath"
