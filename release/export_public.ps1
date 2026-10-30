[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$Destination = ""
)

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($ProjectRoot)
if (-not $Destination) {
    $Destination = Join-Path $root 'publish\v1.0.0\repository'
}
$destinationFull = [IO.Path]::GetFullPath($Destination)
$publishRoot = [IO.Path]::GetFullPath((Join-Path $root 'publish\v1.0.0'))
if (-not $destinationFull.StartsWith($publishRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to export outside $publishRoot"
}
if ($destinationFull -eq $publishRoot) {
    throw 'Destination must be the repository child directory.'
}

if (Test-Path -LiteralPath $destinationFull) {
    Remove-Item -LiteralPath $destinationFull -Recurse -Force
}
New-Item -ItemType Directory -Path $destinationFull -Force | Out-Null

function Copy-PublicFile {
    param([string]$Source, [string]$Relative)
    $sourceFull = Join-Path $root $Source
    if (-not (Test-Path -LiteralPath $sourceFull -PathType Leaf)) {
        throw "Required source file is missing: $Source"
    }
    $target = Join-Path $destinationFull $Relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Copy-Item -LiteralPath $sourceFull -Destination $target -Force
}

function Copy-PublicTree {
    param([string]$Source, [string]$Relative, [string[]]$Include = @('*'))
    $sourceFull = Join-Path $root $Source
    $target = Join-Path $destinationFull $Relative
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    foreach ($pattern in $Include) {
        Get-ChildItem -LiteralPath $sourceFull -File -Recurse -Filter $pattern | ForEach-Object {
            if ($_.FullName -match '[\\/]__pycache__[\\/]') { return }
            $child = [IO.Path]::GetRelativePath($sourceFull, $_.FullName)
            $out = Join-Path $target $child
            New-Item -ItemType Directory -Path (Split-Path -Parent $out) -Force | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $out -Force
        }
    }
}

Copy-PublicTree 'release\repository' '.'

$pythonSources = @(
    'adapters.py','api_connector.py','app_settings.py','chat_archive.py','connections.py',
    'context_search.py','core.py','desktop.py','desktop_control.py','desktop_mcp.py',
    'discovery.py','file_library.py','friendly.py','launch.pyw','memory_agent.py',
    'native_instance.py','native_services.py','quotas.py','rpc.py','server.py',
    'skill_library.py','uploads.py','windows_desktop.py','workflow.py'
)
foreach ($name in $pythonSources) { Copy-PublicFile $name $name }
Copy-PublicFile 'deepseek-account.patch.yml' 'config/deepseek-account.patch.example.yml'

Copy-PublicTree 'ui' 'ui' @('*.html','*.css','*.js')
$assetNames = @(
    'codex.png','deepseek.png','file-archive.png','file-audio.png','file-code.png',
    'file-generic.png','file-image.png','file-pdf.png','file-ppt.png','file-sheet.png',
    'file-text.png','file-video.png','file-word.png','group.svg','user.svg',
    'installed-claude.png','installed-codex.png','installed-deepseek.png','installed-doubao.png',
    'installed-ollama.png','installed-qwen.png','installed-workbuddy.png',
    'superteam-v1.png','superteam-v1.ico'
)
foreach ($name in $assetNames) { Copy-PublicFile "ui\assets\$name" "ui\assets\$name" }

Copy-PublicTree 'tests' 'tests' @('test_*.py','*.cjs','*.mjs')
Copy-PublicFile 'release\audit_public.py' 'release/audit_public.py'
Copy-PublicFile 'release\build_portable.ps1' 'release/build_portable.ps1'
Copy-PublicFile 'release\export_public.ps1' 'release/export_public.ps1'
Copy-PublicFile 'release\SuperTeam.iss' 'release/SuperTeam.iss'
Copy-PublicFile 'release\SuperTeam.spec' 'release/SuperTeam.spec'
Copy-PublicFile 'release\SuperTeamComputer.spec' 'release/SuperTeamComputer.spec'
Copy-PublicFile 'release\install-smoke.ps1' 'release/install-smoke.ps1'
Copy-PublicFile 'release\finalize_release.ps1' 'release/finalize_release.ps1'
Copy-PublicFile 'work\pyinstaller-hooks\hook-workflow.py' 'release/pyinstaller-hooks/hook-workflow.py'

$iconSource = Join-Path $root 'ui\assets\superteam-v1.png'
$iconTarget = Join-Path $destinationFull 'docs\images\superteam-icon.png'
New-Item -ItemType Directory -Path (Split-Path -Parent $iconTarget) -Force | Out-Null
Copy-Item -LiteralPath $iconSource -Destination $iconTarget -Force

$auditJson = Join-Path $publishRoot 'public-audit.json'
& python (Join-Path $root 'release\audit_public.py') $destinationFull --json $auditJson
if ($LASTEXITCODE -ne 0) { throw 'Public source audit failed.' }
Write-Output "PUBLIC_REPOSITORY=$destinationFull"
Write-Output "AUDIT=$auditJson"

