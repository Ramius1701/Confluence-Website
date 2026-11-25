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

# The build runs in its own Python environment, .venv\ beside this script (made on first run), so it never depends
# on packages installed per user, which a scheduled task may not see.
$py = Join-Path $src '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    python -m venv (Join-Path $src '.venv')
    if ($LASTEXITCODE -ne 0) { throw "could not create $src\.venv" }
}
& $py -c "import importlib.util, sys; sys.exit(importlib.util.find_spec('markdown') is None)"
if ($LASTEXITCODE -ne 0) {
    & $py -m pip install --quiet --disable-pip-version-check -r (Join-Path $src 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw "could not install the build's requirements" }
}

$buildArgs = @("$src\build.py")
if (-not $NoFetch) { $buildArgs += '--fetch' }
& $py @buildArgs
if ($LASTEXITCODE -ne 0) { throw "build failed (exit $LASTEXITCODE); nothing was published" }

New-Item -ItemType Directory -Force $Target | Out-Null
robocopy "$src\dist" $Target /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
# robocopy: 0-7 are success (8 and above are failures).
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE" }

$count = (Get-ChildItem $Target -Recurse -File).Count
Write-Host "Published $count files to $Target"
exit 0   # robocopy's 1-7 ("files copied") would otherwise become this script's exit code
