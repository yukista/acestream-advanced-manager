$json = Get-Content 'clashsports.json' -Raw
$data = $json | ConvertFrom-Json
$channels = @()
$seen = @()
$invalid = 0

foreach ($grp in $data.groups) {
    foreach ($st in $grp.stations) {
        if ($st.url -like "acestream://*") {
            $h = $st.url.Replace("acestream://", "")
            if ($h.Length -eq 40) {
                if ($h -notmatch "^[a-f0-9]{40}$") {
                    $invalid++
                    Write-Host "INVALID: $h" -ForegroundColor Red
                } elseif ($h -notin $seen) {
                    $seen += $h
                    $channels += @{ t = "$($grp.name) - $($st.name) [$($st.info)]"; h = $h }
                }
            }
        }
    }
}

Write-Host ""
Write-Host "Total: Válidos=$($channels.Count) Inválidos=$invalid" -ForegroundColor Green
Write-Host ""

$ok = 0; $dup = 0; $err = 0
$channels | ForEach-Object {
    try {
        $body = @{title = $_.t; hash = $_.h} | ConvertTo-Json -Compress
        Invoke-RestMethod -Uri "http://127.0.0.1:8001/channels" -Method POST -ContentType "application/json" -Body $body | Out-Null
        Write-Host "[+] $($_.h.Substring(0,6))" -ForegroundColor Green
        $ok++
    } catch {
        $code = $_.Exception.Response.StatusCode
        if ($code -eq 409) { $dup++ }
        else { $err++ }
    }
}

Write-Host ""
Write-Host "Resultat: Afegits=$ok Duplicats=$dup Errors=$err" -ForegroundColor Green
