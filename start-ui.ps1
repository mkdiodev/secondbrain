$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "Virtualenv Python not found: $VenvPython"
}

Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -eq "python.exe" -and
        $_.CommandLine -like "*secondbrain.cli ui*"
    } |
    ForEach-Object {
        try {
            Stop-Process -Id $_.ProcessId -Force
            Write-Host "Stopped old UI process PID=$($_.ProcessId)"
        } catch {
            Write-Host "Old UI process already stopped PID=$($_.ProcessId)"
        }
    }

Set-Location -LiteralPath $ProjectRoot
Write-Host "Starting SecondBrain UI with: $VenvPython"
& $VenvPython -m secondbrain.cli ui
