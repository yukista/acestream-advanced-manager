try {
    $body = @{
        title = "Test"
        hash = "8c67cdb5ba81976662c3a67984a9545d9cfb0f70"
    } | ConvertTo-Json

    Write-Host "Enviando a: http://127.0.0.1:8001/channels" -ForegroundColor Cyan
    Write-Host "Body: $body" -ForegroundColor Cyan

    $result = Invoke-RestMethod -Uri "http://127.0.0.1:8001/channels" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body

    Write-Host "Exito: $result" -ForegroundColor Green
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Response: $($_.Exception.Response)" -ForegroundColor Red
}
