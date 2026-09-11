param(
  [string]$TaskName = "Baltigo Shop Cloud Agent"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\pythonw.exe"
$Agent = Join-Path $Root "agent.py"
$EnvFile = Join-Path $Root ".env"

if (!(Test-Path $Python)) {
  throw "Virtual environment not found. Run: py -m venv .venv; .\.venv\Scripts\pip.exe install -r requirements.txt"
}
if (!(Test-Path $Agent)) { throw "agent.py not found" }
if (!(Test-Path $EnvFile)) { throw ".env not found. Copy .env.example to .env and configure pairing first." }

# OBS Virtual Camera and browsers live in an interactive desktop session. Therefore the
# agent starts at user logon rather than as a Session 0 Windows service.
$Action = New-ScheduledTaskAction -Execute $Python -Argument ('"' + $Agent + '"') -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "Installed and started: $TaskName"
