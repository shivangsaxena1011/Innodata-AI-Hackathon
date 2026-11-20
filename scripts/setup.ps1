# CodeForge AI setup for Windows (PowerShell). Free of cost: Gemini free tier + optional Ollama.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
}

# Prefer a signed system Python 3.12 (Smart App Control can block uv-downloaded interpreters).
$py = $null
try { $py = (& py -3.12 -c "import sys; print(sys.executable)") } catch { }
if ($py) { uv venv --python $py } else { uv venv --python 3.12 }
uv sync

if (-not (Get-Command harbor -ErrorAction SilentlyContinue) -and
    -not (Test-Path "$env:USERPROFILE\.local\bin\harbor.exe")) {
    uv tool install harbor
}
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env"; Write-Host "Created .env: add GEMINI_API_KEY" }

.\.venv\Scripts\python.exe -m codeforge.main doctor
