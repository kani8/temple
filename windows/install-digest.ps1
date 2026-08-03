<#
.SYNOPSIS
    Schedule the combined morning digest (Prep-U + Fitness OS) on this machine.

.DESCRIPTION
    Registers a daily task that runs `fitness-os daily --digest`, which emails
    one brief containing the day's study assignment and the day's training and
    nutrition plan.

    This runs locally rather than in GitHub Actions on purpose: the Prep-U half
    needs progress.json from this machine to show an accurate streak and mark
    solved problems. A cloud runner cannot see it.

    Requires SMTP_HOST / SMTP_PORT / SMTP_USERNAME / SMTP_PASSWORD /
    EMAIL_FROM / EMAIL_TO as user environment variables.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install-digest.ps1
    powershell -ExecutionPolicy Bypass -File install-digest.ps1 -At 06:30
    powershell -ExecutionPolicy Bypass -File install-digest.ps1 -TestOnly
    powershell -ExecutionPolicy Bypass -File install-digest.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [string]$At = '06:00',
    [string]$PrepURepo = "$env:USERPROFILE\projects\interview-prep-questions",
    [switch]$TestOnly,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$Here     = Split-Path -Parent $MyInvocation.MyCommand.Path
$Repo     = Split-Path -Parent $Here
$TaskName = 'Fitness OS Morning Digest'

if ($Uninstall) {
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($t) { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false; Write-Host "removed '$TaskName'" }
    else { Write-Host 'nothing to remove' }
    return
}

Write-Host 'Fitness OS digest installer'
Write-Host "  repo    : $Repo"
Write-Host "  prep-u  : $PrepURepo"

# ---------------------------------------------------------------- preflight
#
# SetEnvironmentVariable(...,'User') writes to the registry; a shell that was
# already open keeps its old copy of the environment. So the registry can hold
# every value while $env: - and therefore any child process we spawn - sees
# none of them. Hydrate the process environment from the User scope first, then
# validate what the child will actually receive.
$required = @('SMTP_HOST', 'SMTP_PORT', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'EMAIL_FROM', 'EMAIL_TO')
foreach ($name in $required) {
    if (-not (Get-Item "env:$name" -ErrorAction SilentlyContinue)) {
        $val = [Environment]::GetEnvironmentVariable($name, 'User')
        if (-not $val) { $val = [Environment]::GetEnvironmentVariable($name, 'Machine') }
        if ($val) { Set-Item "env:$name" $val }
    }
}

$mandatory = @('SMTP_HOST', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'EMAIL_FROM', 'EMAIL_TO')
$missing = $mandatory | Where-Object { -not (Get-Item "env:$_" -ErrorAction SilentlyContinue) }
if ($missing) {
    throw @"
Missing SMTP settings: $($missing -join ', ')

Set them as *User* environment variables, for example:
  [Environment]::SetEnvironmentVariable('SMTP_HOST','smtp.gmail.com','User')

For Gmail, SMTP_PASSWORD must be a 16-character App Password from
https://myaccount.google.com/apppasswords - not your account password.

If you just set them, this script now reads them straight from the registry,
so you should not need a new shell. Verify with:
  [Environment]::GetEnvironmentVariable('SMTP_HOST','User')
"@
}
Write-Host "  smtp    : $($mandatory.Count) variables loaded (user -> $env:EMAIL_TO)"

if (-not (Test-Path (Join-Path $PrepURepo 'platform\scripts\daily_brief.py'))) {
    Write-Warning "Prep-U not found at $PrepURepo - the digest will send fitness-only."
    Write-Warning 'Pass -PrepURepo <path> if it lives elsewhere.'
} else {
    Write-Host '  prep-u  : found'
}

# fitness-os must be importable; prefer the console script, fall back to -m.
$cmd = Get-Command 'fitness-os' -ErrorAction SilentlyContinue
if ($cmd) {
    $exe = $cmd.Source
    $arguments = 'daily --digest'
} else {
    . (Join-Path $PrepURepo 'windows\lib-python.ps1') -ErrorAction SilentlyContinue
    $py = Get-Command 'py' -ErrorAction SilentlyContinue
    if (-not $py) { throw "Neither 'fitness-os' nor 'py' found. Run: python -m pip install -e `"$Repo`"" }
    $exe = $py.Source
    $arguments = "-3 -m fitness_os.cli daily --digest"
    Write-Warning "'fitness-os' not on PATH; using '$exe $arguments'."
}
Write-Host "  command : $exe $arguments"

# ---------------------------------------------------------------- test send
if ($TestOnly) {
    Write-Host ''
    Write-Host 'Sending a test digest now...' -ForegroundColor Cyan
    $env:PREPU_REPO = $PrepURepo
    & $exe $arguments.Split(' ')
    if ($LASTEXITCODE -eq 0) { Write-Host 'Sent. Check your inbox.' -ForegroundColor Green }
    else { Write-Host "Failed with exit code $LASTEXITCODE." -ForegroundColor Red }
    return
}

# ---------------------------------------------------------------- schedule
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($t) { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false }

# PREPU_REPO has to reach the task's process, and Task Scheduler does not expand
# user env vars reliably, so pass it explicitly through a cmd wrapper.
$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\cmd.exe" `
    -Argument "/c set PREPU_REPO=$PrepURepo&& `"$exe`" $arguments" `
    -WorkingDirectory $Repo

$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description 'Emails one combined morning brief: Prep-U study plan + Fitness OS training and nutrition.' | Out-Null

Write-Host ''
Write-Host "Scheduled '$TaskName' daily at $At." -ForegroundColor Green
Write-Host 'StartWhenAvailable is on, so a missed run (machine asleep) fires when you next wake it.'
Write-Host ''
Write-Host 'Send one right now to confirm:'
Write-Host "  powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`" -TestOnly"
Write-Host ''
Write-Host "Remove with:  install-digest.ps1 -Uninstall"
