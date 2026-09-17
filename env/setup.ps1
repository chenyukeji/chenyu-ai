param([string]$PythonExecutable = "")

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$venvPath = Join-Path $PSScriptRoot '.venv'
$venvPython = Join-Path $venvPath 'Scripts\python.exe'

$codexPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not $PythonExecutable) {
    if (Test-Path -LiteralPath $codexPython) {
        $PythonExecutable = $codexPython
    } else {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (-not $pythonCommand) {
            throw 'Python 3.10+ was not found. Pass -PythonExecutable with its full path.'
        }
        $PythonExecutable = $pythonCommand.Source
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    & $PythonExecutable -m venv $venvPath
}

& $venvPython -m pip install --upgrade pip setuptools
& $venvPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
& $venvPython -m pip install -e $projectRoot

$codexNodeModules = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
$envNodeModules = Join-Path $PSScriptRoot 'node_modules'
if ((Test-Path -LiteralPath $codexNodeModules) -and -not (Test-Path -LiteralPath $envNodeModules)) {
    New-Item -ItemType Junction -Path $envNodeModules -Target $codexNodeModules | Out-Null
}

Write-Output "Environment ready: $venvPython"
