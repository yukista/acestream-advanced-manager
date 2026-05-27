param(
    [string]$SourceFile = "clashsports.json",
    [string]$BackendBaseUrl = "http://127.0.0.1:8001",
    [int]$DelayMs = 50
)

if (-not (Test-Path $SourceFile)) {
    Write-Error "Source file not found: $SourceFile"
    exit 1
}

$raw = Get-Content $SourceFile -Raw
$data = $raw | ConvertFrom-Json

$channels = [System.Collections.Generic.List[object]]::new()
$seen = [System.Collections.Generic.HashSet[string]]::new()
$invalid = 0

foreach ($group in $data.groups) {
    if (-not $group.stations) {
        continue
    }

    foreach ($station in $group.stations) {
        if (-not $station.url -or -not ($station.url -like "acestream://*")) {
            continue
        }

        $hash = $station.url.Replace("acestream://", "").ToLower()

        if (-not ($hash -match "^[a-f0-9]{40}$")) {
            $invalid++
            continue
        }

        if ($seen.Add($hash)) {
            $title = "$($station.name) [$($station.info)]"
            $channels.Add(@{ title = $title; hash = $hash })
        }
    }
}

Write-Host ""
Write-Host "Prepared channels: $($channels.Count)" -ForegroundColor Green
Write-Host "Invalid hashes skipped: $invalid" -ForegroundColor Yellow
Write-Host ""

$added = 0
$duplicates = 0
$errors = 0
$target = "$($BackendBaseUrl.TrimEnd('/'))/channels"

foreach ($ch in $channels) {
    try {
        $body = @{ title = $ch.title; hash = $ch.hash } | ConvertTo-Json -Compress

        Invoke-RestMethod -Uri $target `
            -Method POST `
            -ContentType "application/json" `
            -Body $body `
            -ErrorAction Stop | Out-Null

        $added++
    }
    catch {
        $code = $null
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $code = [int]$_.Exception.Response.StatusCode
        }

        if ($code -eq 409) {
            $duplicates++
        }
        else {
            $errors++
            Write-Host "Request failed for $($ch.hash.Substring(0, 8)) (HTTP $code)" -ForegroundColor Red
        }
    }

    if ($DelayMs -gt 0) {
        Start-Sleep -Milliseconds $DelayMs
    }
}

Write-Host ""
Write-Host "Import summary" -ForegroundColor Cyan
Write-Host "  Added: $added" -ForegroundColor Green
Write-Host "  Duplicates: $duplicates" -ForegroundColor Yellow
Write-Host "  Errors: $errors" -ForegroundColor Red
Write-Host ""
