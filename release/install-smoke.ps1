[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Installer,
    [string]$TestDir = "$env:LOCALAPPDATA\SuperTeam-Install-Smoke"
)

$ErrorActionPreference='Stop'
$installerFull=[IO.Path]::GetFullPath($Installer)
if (-not (Test-Path -LiteralPath $installerFull)) { throw 'Installer not found.' }
$testFull=[IO.Path]::GetFullPath($TestDir)
if (-not $testFull.StartsWith([IO.Path]::GetFullPath($env:LOCALAPPDATA),[StringComparison]::OrdinalIgnoreCase)) {
    throw 'Smoke install must stay inside LOCALAPPDATA.'
}
if (Test-Path -LiteralPath $testFull) { Remove-Item -LiteralPath $testFull -Recurse -Force }

$install=Start-Process -FilePath $installerFull -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',"/DIR=$testFull") -Wait -PassThru
if ($install.ExitCode -ne 0) { throw "Installer exited $($install.ExitCode)" }
$exe=Join-Path $testFull 'SuperTeam.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw 'Installed executable missing.' }

$env:SUPERTEAM_ROOT=$testFull
$process=Start-Process -FilePath $exe -ArgumentList '--server' -WorkingDirectory $testFull -PassThru -WindowStyle Hidden
$runtime=Join-Path $testFull 'data\runtime.json'
$healthy=$false
for($i=0;$i -lt 100;$i++){
    Start-Sleep -Milliseconds 150
    if(Test-Path -LiteralPath $runtime){
        try{
            $info=Get-Content -LiteralPath $runtime -Raw | ConvertFrom-Json
            $health=Invoke-RestMethod -Uri "http://127.0.0.1:$($info.port)/health" -TimeoutSec 2
            if($health.app -eq 'ai-chat-sandbox'){$healthy=$true;break}
        }catch{}
    }
}
if(-not $healthy){
    if(-not $process.HasExited){Stop-Process -Id $process.Id -Force}
    throw 'Installed app did not reach its health endpoint.'
}
$headers=@{'X-App-Token'=$info.token}
Invoke-RestMethod -Uri "http://127.0.0.1:$($info.port)/api/shutdown" -Method Post -Headers $headers -ContentType 'application/json' -Body '{}' | Out-Null
try{Wait-Process -Id $process.Id -Timeout 30 -ErrorAction Stop}catch{if(-not $process.HasExited){Stop-Process -Id $process.Id -Force}}

$uninstaller=Join-Path $testFull 'unins000.exe'
if(-not (Test-Path -LiteralPath $uninstaller)){throw 'Uninstaller missing.'}
$uninstall=Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') -Wait -PassThru
if($uninstall.ExitCode -ne 0){throw "Uninstaller exited $($uninstall.ExitCode)"}
Start-Sleep -Milliseconds 500
if(Test-Path -LiteralPath $exe){throw 'Uninstall left the executable behind.'}
[pscustomobject]@{installed=$true;health=$true;uninstalled=$true;testDir=$testFull} | ConvertTo-Json

