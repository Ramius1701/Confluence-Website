# Publishes the website to Laragon, where Apache serves it as https://confluence.ddns.net
# (S:\laragon\etc\apache2\sites-enabled\zzz-public-confluence.conf).
#   .\Deploy.ps1                 copy the site to S:\laragon\www\confluence
#   .\Deploy.ps1 -Target <dir>   copy it somewhere else
# Only the site's own files are copied (pages, style.css, assets); the repo's .git, README and this script stay out.
# The target is mirrored: files deleted from the site are deleted there too.
param([string]$Target = 'S:\laragon\www\confluence')

$ErrorActionPreference = 'Stop'
$src = $PSScriptRoot
New-Item -ItemType Directory -Force $Target | Out-Null

robocopy $src $Target /MIR /XD .git .claude /XF README.md Deploy.ps1 .gitignore /NFL /NDL /NJH /NJS /NP | Out-Null
# robocopy: 0-7 are success (8 and above are failures).
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE" }

Write-Host "Deployed to $Target"
Get-ChildItem $Target -Recurse -File | ForEach-Object { '  ' + $_.FullName.Substring($Target.Length + 1) }
