# Lance l'API (interface collections vectorielles sur http://localhost:8000/)
# Utilisez ce script si "python" ou "py" ne sont pas dans le PATH.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = $null

# 1) Venv du projet
$venv = Join-Path $PSScriptRoot "venv", "Scripts", "python.exe"
if (Test-Path $venv) { $python = $venv }

# 2) Commandes dans le PATH
if (-not $python) {
    foreach ($cmd in @("python", "py", "python3")) {
        $p = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($p) { $python = $cmd; break }
    }
}

# 3) Emplacements d'installation classiques
if (-not $python) {
    $paths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python*\python.exe",
        "$env:ProgramFiles\Python*\python.exe"
    )
    foreach ($pattern in $paths) {
        $found = Get-Item $pattern -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { $python = $found.FullName; break }
    }
}

if (-not $python) {
    Write-Host "Python introuvable. Installez Python ou ajoutez-le au PATH." -ForegroundColor Red
    Write-Host "Puis lancez : python -m uvicorn app.main:app --reload" -ForegroundColor Yellow
    exit 1
}

Write-Host "Lancement avec : $python -m uvicorn app.main:app --reload" -ForegroundColor Cyan
Write-Host "Interface : http://localhost:8000/" -ForegroundColor Green
& $python -m uvicorn app.main:app --reload
