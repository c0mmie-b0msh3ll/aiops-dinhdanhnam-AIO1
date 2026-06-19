param(
    [string]$Service = "payment-svc",
    [int]$DurationSeconds = 90,
    [int]$IntervalMilliseconds = 250
)

$ports = @{
    "frontend" = 8080
    "api-gateway" = 8081
    "payment-svc" = 8082
    "inventory-svc" = 8083
    "checkout-svc" = 8084
}

if (-not $ports.ContainsKey($Service)) {
    Write-Output "Unknown service '$Service'. Valid: $($ports.Keys -join ', ')"
    exit 1
}

$url = "http://localhost:$($ports[$Service])/"
$deadline = (Get-Date).AddSeconds($DurationSeconds)
$ok = 0
$fail = 0

Write-Output "[Invoke-Traffic] Sending traffic to $Service at $url for $DurationSeconds seconds..."
while ((Get-Date) -lt $deadline) {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 5 | Out-Null
        $ok += 1
    } catch {
        $fail += 1
    }
    Start-Sleep -Milliseconds $IntervalMilliseconds
}

Write-Output "[Invoke-Traffic] Complete. ok=$ok fail=$fail"
