param(
    [ValidateSet("list", "stop")]
    [string]$Action = "list"
)

$ErrorActionPreference = "Stop"

# Find any process launched from current or older remap startup paths.
$patterns = @(
    "remap-key.py",
    "run-remap-key-hidden.vbs",
    "run-remap-key.cmd"
)

$procs = Get-CimInstance Win32_Process |
        Where-Object {
            ($_.Name -in @("python.exe", "pythonw.exe", "wscript.exe", "cscript.exe", "cmd.exe", "remap-key.exe")) -and
            $_.CommandLine
        }

$foundProcesses = @()
foreach ($p in $procs) {
    # Always include remap-key.exe by name, regardless of command line
    if ($p.Name -eq "remap-key.exe") {
        $foundProcesses += $p
        continue
    }
    $line = [string]$p.CommandLine
    foreach ($pat in $patterns) {
        if ($line -match [regex]::Escape($pat)) {
            $foundProcesses += $p
            break
        }
    }
}

$foundProcesses = $foundProcesses | Sort-Object ProcessId -Unique

if (-not $foundProcesses) {
    Write-Host "No remap-related processes found."
    exit 0
}

if ($Action -eq "list") {
    $foundProcesses |
        Select-Object ProcessId, Name, CommandLine |
        Format-Table -AutoSize
    exit 0
}

$killed = @()
$failed = @()
foreach ($m in $foundProcesses) {
    try {
        Stop-Process -Id $m.ProcessId -Force -ErrorAction Stop
        $killed += $m
    }
    catch {
        $failed += [pscustomobject]@{
            ProcessId = $m.ProcessId
            Name      = $m.Name
            Error     = $_.Exception.Message
        }
    }
}

if ($killed) {
    Write-Host "Stopped remap-related processes:"
    $killed | Select-Object ProcessId, Name, CommandLine | Format-Table -AutoSize
}
if ($failed) {
    Write-Warning "Some processes could not be stopped:"
    $failed | Format-Table -AutoSize
    exit 1
}

exit 0
