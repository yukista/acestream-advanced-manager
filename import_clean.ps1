[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$json = Get-Content 'clashsports.json' -Raw
$data = $json | ConvertFrom-Json
$all_channels = @()

foreach ($grp in $data.groups) {
    foreach ($st in $grp.stations) {
        if ($st.url -like "acestream://*") {
            $h = $st.url.Replace("acestream://", "")
            if ($h.Length -eq 40 -and $h -match "^[a-f0-9]{40}$") {
                # Simple title without emojis
                $simple_title = $st.name
                $all_channels += @{ 
                    title = $simple_title
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

Write-Host ""
Write-Host "Canals únics a importar: $($channels.Count)" -ForegroundColor Green

$added = 0
$exists = 0
$failed = 0
$count = 0

$channels | ForEach-Object {
    $count++
    $ch = $_
    $pct = [int](($count * 100) / $channels.Count)
    
    try {
        $body = @{
            title = $ch.title
            hash = $ch.hash
        } | ConvertTo-Json -Compress
        
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8001/channels" `
            -Method POST `
            -ContentType "application/json" `
            -Body $body `
            -ErrorAction Stop
        
        Write-Host "[$pct%] + $($ch.hash.Substring(0,6))" -ForegroundColor Green
        $added++
    } catch {
        $status = $_.Exception.Response.StatusCode
        if ($status -eq 409) {
            Write-Host "[$pct%] * $($ch.hash.Substring(0,6)) (duplicate)" -ForegroundColor Yellow
            $exists++
        } else {
            Write-Host "[$pct%] ! $($ch.hash.Substring(0,6)) ($status)" -ForegroundColor Red
            $failed++
        }
    }
}

Write-Host ""
Write-Host "Resultat Final:" -ForegroundColor Cyan
Write-Host "  Afegits: $added" -ForegroundColor Green
Write-Host "  Existents: $exists" -ForegroundColor Yellow  
Write-Host "  Errors: $failed" -ForegroundColor Red
Write-Host ""
