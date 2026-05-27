# Script per importar canals des del JSON de ClashSports

$json = @'
{"name":"  ClashSports [GH]⚽️🚲🏀🎾🏎🏁",
 "author":"Colás - Actualizado 21/02/2026 10:30",
 "url":"https://raw.githubusercontent.com/ClashUnico/Wise/refs/heads/main/Clashsports.w3u",
 "image":"https://cdn.pixabay.com/photo/2016/01/20/10/46/soccer-1151288_1280.jpg",
 "imageScale":"",
 "contact":"",
 "info":"",
 "groups":[
      {"logo":"♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️♦️",
         "name":"Acestream🇪🇸",
         "info":"Deoprtes Acestream",
         "image":"https://droix.net/blogs/wp-content/uploads/2021/09/AceStream-1024x1024-1.png",
         "stations":[
            {"name":"Movistar Plus+","info":"New Era [FHD]","image":"https://images.seeklogo.com/logo-png/42/1/movistar-plus-logo-png_seeklogo-426538.png","url":"acestream://8c67cdb5ba81976662c3a67984a9545d9cfb0f70","isHost":false},
            {"name":"Movistar Plus+","info":"New Era [FHD]","image":"https://images.seeklogo.com/logo-png/42/1/movistar-plus-logo-png_seeklogo-426538.png","url":"acestream://b6ffbbc72a5b6b579faf79ebac229af7a25b933b","isHost":false},
            {"name":"Movistar Plus+","info":"Elcano [FHD]","image":"https://images.seeklogo.com/logo-png/42/1/movistar-plus-logo-png_seeklogo-426538.png","url":"acestream://d23497596720b47b096ec0f850d6d26a19d1a336","isHost":false},
            {"name":"Movistar Plus+","info":"Elcano [FHD]","image":"https://images.seeklogo.com/logo-png/42/1/movistar-plus-logo-png_seeklogo-426538.png","url":"acestream://1ab443f5b4beb6d586f19e8b25b9f9646cf2ab78","isHost":false},
            {"name":"DAZN LaLiga","info":"New Era","image":"https://telegra.ph/file/083da39b90492923b30d4.jpg","url":"acestream://19f28f60c908f987b1a03da078e63320d7bf29e8","isHost":false},
            {"name":"DAZN LaLiga","info":"New Era [FHD]","image":"https://telegra.ph/file/083da39b90492923b30d4.jpg","url":"acestream://d1596a3988b84a4d2711fd380eb8a53256ad74ae","isHost":false},
            {"name":"DAZN LaLiga","info":"Sport TV","image":"https://telegra.ph/file/083da39b90492923b30d4.jpg","url":"acestream://dda5d2cace9bc4cb0918e62bc50d657d4a10496a","isHost":false},
            {"name":"M+ LaLiga","info":"New Era [FHD]","image":"https://telegra.ph/file/ede750e0a9de6e726a3f7.jpg","url":"acestream://af458073c3096293a4dea9f369d4f308e7125bd6","isHost":false},
            {"name":"M+ LaLiga","info":"New Era II [FHD]","image":"https://telegra.ph/file/ede750e0a9de6e726a3f7.jpg","url":"acestream://d4ff041287a43e3114d411d671c4b4e92e21f33y","isHost":false},
            {"name":"M+ LaLiga","info":"Sport TV","image":"https://telegra.ph/file/ede750e0a9de6e726a3f7.jpg","url":"acestream://31c19ffb3472c289c5bbbbc174449c8ed0d19e38","isHost":false}
         ]}
   ]}
'@

$data = $json | ConvertFrom-Json

$channels = @()
$channelSet = [System.Collections.Generic.HashSet[string]]::new()

foreach ($group in $data.groups) {
    if ($group.stations) {
        foreach ($station in $group.stations) {
            if ($station.url -match "acestream://(.+)") {
                $hash = $matches[1]
                if ($hash -and $hash.length -eq 40 -and $channelSet.Add($hash)) {
                    $title = "$($station.name) - $($station.info)"
                    $channels += @{ title = $title; hash = $hash }
                }
            }
        }
    }
}

Write-Host "Total canals únics a afegir: $($channels.Count)" -ForegroundColor Green

$baseURL = "http://127.0.0.1:8001"
$successCount = 0
$failCount = 0

foreach ($ch in $channels) {
    try {
        $body = @{
            title = $ch.title
            hash = $ch.hash
        } | ConvertTo-Json

        $response = Invoke-RestMethod -Uri "$baseURL/api/channels" `
            -Method POST `
            -ContentType "application/json" `
            -Body $body `
            -ErrorAction Stop

        Write-Host "✓ $($ch.hash.Substring(0,8))... - $($ch.title)" -ForegroundColor Green
        $successCount++
    }
    catch {
        Write-Host "✗ Failed: $($ch.hash.Substring(0,8))... - $($_.Exception.Message)" -ForegroundColor Red
        $failCount++
    }
    
    Start-Sleep -Milliseconds 100
}

Write-Host "`n✓ Afegits: $successCount" -ForegroundColor Green
Write-Host "✗ Fallats: $failCount" -ForegroundColor Red
