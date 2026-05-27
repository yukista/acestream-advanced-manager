$json = Get-Content 'clashsports.json' -Raw
$data = $json | ConvertFrom-Json
$all_channels = @()

foreach ($grp in $data.groups) {
    foreach ($st in $grp.stations) {
        if ($st.url -like "acestream://*") {
            $h = $st.url.Replace("acestream://", "")
            if ($h.Length -eq 40 -and $h -match "^[a-f0-9]{40}$") {
                $all_channels += @{ 
                    title = "$($grp.name) [$($st.name)]"
                    hash = $h
                }
            }
        }
    }
}

$seen = @{}
$channels = @()
foreach ($ch in $all_channels) {
    if (-not $seen[$ch.hash]) {
        $seen[$ch.hash] = $true
        $channels += $ch
    }
}

Write-Host "Canals: $($channels.Count)" -ForegroundColor Green

if ($channels.Count -gt 0) {
    $first = $channels[0]
    Write-Host ""
    Write-Host "Primer canal a importar: " -ForegroundColor Cyan
    Write-Host "  Title: $($first.title)" 
    Write-Host "  Hash: $($first.hash)"
    Write-Host ""

    # Test with first channel
    $body = @{
        title = $first.title
        hash = $first.hash
    } | ConvertTo-Json -Compress
    
    Write-Host "JSON Body: $body" -ForegroundColor Yellow
    Write-Host ""
    
    try {
        Write-Host "Enviant request..." -ForegroundColor Cyan
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8001/channels" `
            -Method POST `
            -ContentType "application/json" `
            -Body $body `
            -Verbose `
            -ErrorAction Stop
        
        Write-Host "Resposta: $($resp.StatusCode)" -ForegroundColor Green
        Write-Host "Contingut: $($resp.Content)" -ForegroundColor Green
    } catch {
        Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "Status: $($_.Exception.Response.StatusCode)" -ForegroundColor Red
        Write-Host "StatusDescription: $($_.Exception.Response.StatusDescription)" -ForegroundColor Red
        
        # Intentar llegir el contingut d'error
        try {
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            $body_error = $reader.ReadToEnd()
            Write-Host "Body Error: $body_error" -ForegroundColor Red
            $reader.Close()
        } catch {
            Write-Host "No es pot llegir error body" -ForegroundColor Yellow
        }
    }
}
