$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ExpectedPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Write-Host "Expected Python:"
Write-Host "  $ExpectedPython"
Write-Host ""

Write-Host "Port 3000 listener:"
$listeners = Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue |
    Where-Object { $_.State -eq "Listen" }
if ($listeners) {
    $listeners | Select-Object LocalAddress, LocalPort, State, OwningProcess | Format-Table -AutoSize
} else {
    Write-Host "  No process is listening on port 3000."
}

Write-Host ""
Write-Host "SecondBrain UI processes:"
$processes = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -eq "python.exe" -and
        $_.CommandLine -like "*secondbrain.cli ui*"
    }
if ($processes) {
    $processes | Select-Object ProcessId, ParentProcessId, ExecutablePath, CommandLine | Format-List

    Write-Host "Verdict:"
    foreach ($process in $processes) {
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ParentProcessId)" -ErrorAction SilentlyContinue
        $isVenv = $process.ExecutablePath -eq $ExpectedPython -or ($parent -and $parent.ExecutablePath -eq $ExpectedPython)
        if ($isVenv) {
            Write-Host "  PID=$($process.ProcessId) is tied to the project .venv."
        } else {
            Write-Host "  PID=$($process.ProcessId) is NOT tied to the project .venv."
        }
    }
} else {
    Write-Host "  No secondbrain.cli ui process is running."
}
