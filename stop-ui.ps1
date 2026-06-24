$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

$processes = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -eq "python.exe" -and
        $_.CommandLine -like "*secondbrain.cli ui*"
    }

if (-not $processes) {
    Write-Host "No secondbrain.cli ui process is running."
} else {
    foreach ($process in $processes) {
        try {
            Stop-Process -Id $process.ProcessId -Force
            Write-Host "Stopped UI process PID=$($process.ProcessId)"
        } catch {
            Write-Host "UI process already stopped PID=$($process.ProcessId)"
        }
    }
}

Start-Sleep -Seconds 1

$listeners = Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue |
    Where-Object { $_.State -eq "Listen" }

if ($listeners) {
    Write-Host "Port 3000 is still in use:"
    $listeners | Select-Object LocalAddress, LocalPort, State, OwningProcess | Format-Table -AutoSize
} else {
    Write-Host "Port 3000 is free."
}
