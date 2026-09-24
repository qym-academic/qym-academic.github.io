# Run from this Windows machine, where the public Scholar profile is accessible.
$ErrorActionPreference = 'Stop'
$site = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $site '.venv\Scripts\python.exe'
$safeSite = $site.Replace('\', '/')
$cache = Join-Path ([System.IO.Path]::GetTempPath()) ('qym-scholar-' + [guid]::NewGuid().ToString('N') + '.json')

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Executable failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Scholar Python environment missing: $python"
}

Push-Location -LiteralPath $site
try {
    $git = @('-c', "safe.directory=$safeSite")
    $dirty = & git @git status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0 -or $dirty) {
        throw 'Working tree has tracked changes; Scholar synchronization did not start.'
    }
    Invoke-Checked git ($git + @('pull', '--ff-only', 'origin', 'main'))

    $env:SCHOLAR_PROFILE_CACHE = $cache
    $env:PYTHONIOENCODING = 'utf-8'
    Invoke-Checked $python @('bin/run_scholar_update.py', 'bin/update_scholar_citations.py', '--timeout', '180')
    Invoke-Checked $python @('bin/run_scholar_update.py', 'bin/update_scholar_publications.py', '--timeout', '300')

    Invoke-Checked git ($git + @('add', '--', '_data/citations.yml', '_pages/publications.md'))
    & git @git diff --staged --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Output 'Scholar sync succeeded; no published data changed.'
    } elseif ($LASTEXITCODE -eq 1) {
        Invoke-Checked git ($git + @('commit', '-m', 'Update Google Scholar citations and publications'))
        Invoke-Checked git ($git + @('push', 'origin', 'main'))
        Write-Output 'Scholar sync succeeded; data committed and pushed.'
    } else {
        throw "Could not inspect staged changes (exit $LASTEXITCODE)."
    }
} finally {
    Remove-Item Env:SCHOLAR_PROFILE_CACHE -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONIOENCODING -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $cache) {
        Remove-Item -LiteralPath $cache -Force
    }
    Pop-Location
}
