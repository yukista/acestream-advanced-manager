$json = Get-Content 'clashsports.json' -Raw
$data = $json | ConvertFrom-Json

Write-Host "Verificant primers hashes..." -ForegroundColor Green

for ($i = 0; $i -lt 5; $i++) {
    $st = $data.groups[0].stations[$i]
    $url = $st.url
    $h = $url.Replace("acestream://", "")
    
    Write-Host "[$i] Hash: $($h.Substring(0,10))..." -ForegroundColor Yellow
    Write-Host "    Length: $($h.Length)" -ForegroundColor Cyan
    Write-Host "    URL: $url" -ForegroundColor Gray
    Write-Host ""
}
