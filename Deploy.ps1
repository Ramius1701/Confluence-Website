# Builds the website and publishes it to Laragon, where Apache serves it as https://confluence.ddns.net
# (S:\laragon\etc\apache2\sites-enabled\zzz-public-confluence.conf).
#   .\Deploy.ps1                 fetch the project repos, build into dist\, copy dist\ to S:\laragon\www\confluence
#   .\Deploy.ps1 -NoFetch        build from what the project repos already have (no git fetch)
#   .\Deploy.ps1 -Target <dir>   publish somewhere else
# The target is mirrored: files no longer in the build are deleted there too.
param(
    [string]$Target = 'S:\laragon\www\confluence',
    [switch]$NoFetch
)

$ErrorActionPreference = 'Stop'
$src = $PSScriptRoot

$buildArgs = @("$src\build.py")
if (-not $NoFetch) { $buildArgs += '--fetch' }
python @buildArgs
if ($LASTEXITCODE -ne 0) { throw "build failed (exit $LASTEXITCODE); nothing was published" }

New-Item -ItemType Directory -Force $Target | Out-Null
robocopy "$src\dist" $Target /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
# robocopy: 0-7 are success (8 and above are failures).
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE" }

$count = (Get-ChildItem $Target -Recurse -File).Count
Write-Host "Published $count files to $Target"
exit 0   # robocopy's 1-7 ("files copied") would otherwise become this script's exit code
