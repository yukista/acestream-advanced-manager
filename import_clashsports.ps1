$json = Get-Content 'clashsports.json' -Raw
$data = $json | ConvertFrom-Json
$channels = @()
$seen = @{}

foreach ($grp in $data.groups) {
    foreach ($st in $grp.stations) {
        if ($st.url -like "acestream://*") {
            $h = $st.url.Replace("acestream://", "")
            if ($h.Length -eq 40 -and -not $seen[$h]) {
                $seen[$h] = $true
                $channels += @{ t = "$($grp.name) - $($st.name) [$($st.info)]"; h = $h }
            }
        }
    }
}

Write-Host "`n✓ Importador ClashSports - Afegint $($channels.Count) canals..." -ForegroundColor Green
$ok = 0; $dup = 0; $err = 0
$channels | ForEach-Object {
    try {
        $b = @{title = $_.t; hash = $_.h} | ConvertTo-Json -Compress
        Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/channels" -Method POST -ContentType "application/json" -Body $b | Out-Null
        Write-Host "  ✓ $($_.h.Substring(0,6))" -ForegroundColor Green
        $ok++
    } catch {
        if ($_.Exception.Response.StatusCode -eq 409) { $dup++ }
        else { $err++; Write-Host "  ✗ $($_.h.Substring(0,6))" -ForegroundColor Red }
    }
}

Write-Host "`n✓ Afegits: $ok  ⚠ Duplicats: $dup  ✗ Errors: $err`n" -ForegroundColor Cyan
