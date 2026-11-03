# W.E.D.N.E.S.D.A.Y. Windows Location Service Helper
# Queries Windows.Devices.Geolocation.Geolocator via WinRT and outputs structured JSON.
param (
    [int]$TimeoutMs = 8000
)

$ErrorActionPreference = 'Stop'

try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime -ErrorAction Stop
} catch {
    [PSCustomObject]@{
        ok = $false
        status = 'Error'
        error = "Failed to load System.Runtime.WindowsRuntime: $($_.Exception.Message)"
    } | ConvertTo-Json -Compress
    exit 0
}

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { 
    $_.Name -eq 'AsTask' -and 
    $_.GetParameters().Count -eq 1 -and 
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' 
})[0]

function Await-WinRtOperation($WinRtTask, $ResultType, $Timeout) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $completed = $netTask.Wait($Timeout)
    if (-not $completed) {
        throw "WinRT asynchronous operation timed out after ${Timeout}ms"
    }
    return $netTask.Result
}

try {
    [Windows.Devices.Geolocation.Geolocator, Windows.Devices.Geolocation, ContentType = WindowsRuntime] | Out-Null
    $locator = [Windows.Devices.Geolocation.Geolocator]::new()
    $status = $locator.LocationStatus.ToString()

    if ($status -eq 'Disabled') {
        [PSCustomObject]@{
            ok = $false
            status = 'Disabled'
            error = 'Windows Location Services are disabled in Windows Settings (Privacy & security > Location)'
        } | ConvertTo-Json -Compress
        exit 0
    }

    if ($status -eq 'NotAvailable') {
        [PSCustomObject]@{
            ok = $false
            status = 'NotAvailable'
            error = 'Location platform or sensor is not available on this Windows device'
        } | ConvertTo-Json -Compress
        exit 0
    }

    # Request Geoposition with timeout
    $asyncOp = $locator.GetGeopositionAsync()
    $pos = Await-WinRtOperation $asyncOp ([Windows.Devices.Geolocation.Geoposition]) $TimeoutMs

    if ($pos -and $pos.Coordinate -and $pos.Coordinate.Point) {
        $coord = $pos.Coordinate
        $tsUtc = $coord.Timestamp.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        [PSCustomObject]@{
            ok = $true
            status = $status
            latitude = [double]$coord.Point.Position.Latitude
            longitude = [double]$coord.Point.Position.Longitude
            accuracy = [double]$coord.Accuracy
            timestamp = $tsUtc
        } | ConvertTo-Json -Compress
    } else {
        [PSCustomObject]@{
            ok = $false
            status = $status
            error = 'Windows Geolocator returned empty position coordinate'
        } | ConvertTo-Json -Compress
    }
} catch {
    $msg = $_.Exception.Message
    $statusVal = if ($status) { $status } else { 'Error' }
    if ($msg -like '*timed out*') {
        $statusVal = 'Timeout'
    }
    [PSCustomObject]@{
        ok = $false
        status = $statusVal
        error = $msg
    } | ConvertTo-Json -Compress
}
