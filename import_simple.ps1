$json = Get-Content 'clashsports.json' -Raw
$data = $json | ConvertFrom-Json
$channels = @()
$seen = @()

foreach ($grp in $data.groups) {
    foreach ($st in $grp.stations) {
        if ($st.url -like "acestream://*") {
            $h = $st.url.Replace("acestream://", "")
            if ($h.Length -eq 40 -and $h -notin $seen) {
                $seen += $h
                $channels += @{ t = "$($grp.name) - $($st.name) [$($st.info)]"; h = $h }
            }
        }
    }
}

Write-Host ""
Write-Host "Importador ClashSports" -ForegroundColor Green
Write-Host "Canals a afegir: $($channels.Count)" -ForegroundColor Green
Write-Host ""

$ok = 0
$dup = 0
$err = 0

$channels | ForEach-Object {
    try {
        $body = @{title = $_.t; hash = $_.h} | ConvertTo-Json -Compress
        Invoke-RestMethod -Uri "http://127.0.0.1:8001/channels" -Method POST -ContentType "application/json" -Body $body | Out-Null
        Write-Host "[+] $($_.h.Substring(0,6))" -ForegroundColor Green
        $ok++
    } catch {
        $code = $_.Exception.Response.StatusCode
        if ($code -eq 409) { 
            $dup++
        } else { 
            $err++
        }
    }
}

Write-Host ""
Write-Host "Resultat: Afegits=$ok Duplicats=$dup Errors=$err" -ForegroundColor Green
Write-Host ""
