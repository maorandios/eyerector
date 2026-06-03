# Stop every process listening on 8011, then start a single API instance (no --reload; avoids duplicate listeners on Windows).
$ErrorActionPreference = "Stop"
$port = 8011
Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
Start-Process python -ArgumentList "-m", "uvicorn", "analyzer_service.main:app", "--host", "127.0.0.1", "--port", "$port" -WorkingDirectory $root -WindowStyle Hidden
Start-Sleep -Seconds 3
python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:$port/health').read().decode())"
