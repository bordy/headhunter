# Runs the weekly four-agent pipeline and logs output to logs\<date>.log.
# Used by the Windows Task Scheduler entry (see README), or run it by hand.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force logs | Out-Null
$log = "logs\$(Get-Date -Format yyyy-MM-dd).log"
python orchestrator.py weekly *>&1 | Tee-Object -FilePath $log
exit $LASTEXITCODE
