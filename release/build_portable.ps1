[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($ProjectRoot)
$publish = Join-Path $root 'publish\v1.0.0'
$buildRoot = Join-Path $publish 'build'
$distRoot = Join-Path $buildRoot 'dist'
$workRoot = Join-Path $buildRoot 'pyinstaller'
$portable = Join-Path $publish 'portable\SuperTeam'
$assets = Join-Path $publish 'release-assets'

foreach ($target in @($buildRoot, (Split-Path -Parent $portable))) {
    $full = [IO.Path]::GetFullPath($target)
    if (-not $full.StartsWith([IO.Path]::GetFullPath($publish), [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe release target: $full"
    }
}

if (-not $SkipBuild) {
    if (Test-Path -LiteralPath $buildRoot) { Remove-Item -LiteralPath $buildRoot -Recurse -Force }
    New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
    & python -m PyInstaller --noconfirm --clean --distpath $distRoot --workpath $workRoot (Join-Path $root 'release\SuperTeam.spec')
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    & python -m PyInstaller --noconfirm --clean --distpath $distRoot --workpath (Join-Path $buildRoot 'computer-pyinstaller') (Join-Path $root 'release\SuperTeamComputer.spec')
    if ($LASTEXITCODE -ne 0) { throw 'Computer companion build failed.' }
}

$built = Join-Path $distRoot 'SuperTeam'
if (-not (Test-Path -LiteralPath (Join-Path $built 'SuperTeam.exe'))) { throw 'Frozen SuperTeam.exe is missing.' }
if (Test-Path -LiteralPath $portable) { Remove-Item -LiteralPath $portable -Recurse -Force }
New-Item -ItemType Directory -Path $portable -Force | Out-Null
Get-ChildItem -LiteralPath $built -Force | Copy-Item -Destination $portable -Recurse -Force

$uiTarget = Join-Path $portable 'ui'
New-Item -ItemType Directory -Path (Join-Path $uiTarget 'assets') -Force | Out-Null
Get-ChildItem -LiteralPath (Join-Path $root 'ui') -File | Copy-Item -Destination $uiTarget -Force
$fixedAssets = @(
    'codex.png','deepseek.png','file-archive.png','file-audio.png','file-code.png','file-generic.png',
    'file-image.png','file-pdf.png','file-ppt.png','file-sheet.png','file-text.png','file-video.png',
    'file-word.png','group.svg','user.svg','installed-claude.png','installed-codex.png',
    'installed-deepseek.png','installed-doubao.png','installed-ollama.png','installed-qwen.png',
    'installed-workbuddy.png','superteam-v1.png','superteam-v1.ico'
)
foreach ($name in $fixedAssets) {
    Copy-Item -LiteralPath (Join-Path $root "ui\assets\$name") -Destination (Join-Path $uiTarget "assets\$name") -Force
}

$toolsTarget = Join-Path $portable 'tools'
New-Item -ItemType Directory -Path $toolsTarget -Force | Out-Null
$bundledNode=Join-Path $root 'tools\node.exe'
$bundledLicense=Join-Path $root 'tools\node-LICENSE.txt'
if(Test-Path -LiteralPath $bundledNode){
    Copy-Item -LiteralPath $bundledNode -Destination $toolsTarget -Force
    if(-not(Test-Path -LiteralPath $bundledLicense)){throw 'Bundled Node requires tools/node-LICENSE.txt.'}
    Copy-Item -LiteralPath $bundledLicense -Destination $toolsTarget -Force
}else{
    $node=(Get-Command node.exe -ErrorAction SilentlyContinue).Source
    if($node){
        Copy-Item -LiteralPath $node -Destination (Join-Path $toolsTarget 'node.exe') -Force
        $version=(& $node --version).Trim().TrimStart('v')
        Invoke-WebRequest -Uri "https://raw.githubusercontent.com/nodejs/node/v$version/LICENSE" -OutFile (Join-Path $toolsTarget 'node-LICENSE.txt')
    }
}
$computerSource = Join-Path $distRoot 'SuperTeamComputer'
if(-not(Test-Path -LiteralPath (Join-Path $computerSource 'SuperTeamComputer.exe'))){throw 'Computer companion is missing.'}
$computerTarget = Join-Path $toolsTarget 'computer'
Copy-Item -LiteralPath $computerSource -Destination $computerTarget -Recurse -Force
@{root='../..'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $computerTarget 'app-root.json') -Encoding utf8

$guide = @'
SuperTeam 1.0.0 · Windows x64

双击 SuperTeam.exe 启动。首次运行会在当前目录创建 data、uploads、work 和 skills。
程序不附带任何账号、API Key 或聊天记录。请在 AI 联系人中扫描已安装软件，或在 API 接入页填写兼容服务。

Double-click SuperTeam.exe to start. User data is created beside the portable app.
No accounts, credentials or conversations are bundled.

安全提示：v1.0 社区版本暂未商业代码签名。请用同一 Release 中的 SHA256SUMS.txt 校验下载文件。
'@
Set-Content -LiteralPath (Join-Path $portable '使用说明.txt') -Value $guide -Encoding utf8

$forbidden = Get-ChildItem -LiteralPath $portable -Recurse -Force | Where-Object {
    $_.Name -eq 'avatar.png' -or $_.Name -like 'installed-app-*' -or $_.FullName -match '[\\/](data|uploads|work|skills)[\\/]'
}
if ($forbidden) { throw "Forbidden portable content: $($forbidden.FullName -join ', ')" }

New-Item -ItemType Directory -Path $assets -Force | Out-Null
$zip = Join-Path $assets 'SuperTeam-1.0.0-Windows-x64-Portable.zip'
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -LiteralPath $portable -DestinationPath $zip -CompressionLevel Optimal
Write-Output "PORTABLE=$portable"
Write-Output "ZIP=$zip"

