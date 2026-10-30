[CmdletBinding()]
param([string]$ProjectRoot=(Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath($ProjectRoot)
$publish=Join-Path $root 'publish\v1.0.0'
$assets=Join-Path $publish 'release-assets'
$repository=Join-Path $publish 'repository'
$required=@('SuperTeam-Setup-1.0.0.exe','SuperTeam-1.0.0-Windows-x64-Portable.zip')
foreach($name in $required){if(-not(Test-Path -LiteralPath (Join-Path $assets $name))){throw "Missing release asset: $name"}}
& python (Join-Path $root 'release\audit_public.py') $repository --json (Join-Path $publish 'public-audit.json')
if($LASTEXITCODE -ne 0){throw 'Public repository audit failed.'}
$hashLines=foreach($name in $required){$h=Get-FileHash -LiteralPath (Join-Path $assets $name) -Algorithm SHA256;"$($h.Hash.ToLower())  $name"}
Set-Content -LiteralPath (Join-Path $assets 'SHA256SUMS.txt') -Value $hashLines -Encoding ascii
$manifest=@"
SuperTeam v1.0.0 发布清单

源码仓库：repository（使用 GitHub Desktop 发布）
Release 附件：
- release-assets\SuperTeam-Setup-1.0.0.exe
- release-assets\SuperTeam-1.0.0-Windows-x64-Portable.zip
- release-assets\SHA256SUMS.txt

不要上传：项目根目录 data、uploads、work、dist、releases、聊天数据库、API 配置、本机头像或 installed-app-随机编号.png。
详细步骤：repository\docs\GITHUB发布指南.md
"@
Set-Content -LiteralPath (Join-Path $publish '发布清单.txt') -Value $manifest -Encoding utf8
Get-Content -LiteralPath (Join-Path $assets 'SHA256SUMS.txt')

