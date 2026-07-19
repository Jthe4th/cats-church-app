param(
  [string]$PrinterName = ""
)

$ErrorActionPreference = "Stop"

function Fail($Message) {
  Write-Host ""
  Write-Host "FAILED: $Message" -ForegroundColor Red
  exit 1
}

Write-Host "Welcome System Windows Printer Diagnostics" -ForegroundColor Cyan
Write-Host ""

if (-not (Get-Command Get-Printer -ErrorAction SilentlyContinue)) {
  Fail "Get-Printer is not available. Run this on the Windows server PC, not from macOS/Linux."
}

$printers = Get-Printer | Sort-Object Name
if (-not $printers) {
  Fail "No Windows printers are installed."
}

Write-Host "Installed printers:" -ForegroundColor Cyan
$printers | Format-Table Name, DriverName, PortName, PrinterStatus, WorkOffline -AutoSize

if (-not $PrinterName) {
  Write-Host ""
  $PrinterName = Read-Host "Enter the exact printer Name to test"
}

if (-not $PrinterName) {
  Fail "Printer name cannot be blank."
}

$printer = Get-Printer -Name $PrinterName -ErrorAction SilentlyContinue
if (-not $printer) {
  Fail "Printer '$PrinterName' was not found. Use the exact Name shown above."
}

Write-Host ""
Write-Host "Testing printer: $PrinterName" -ForegroundColor Cyan
Write-Host "Driver: $($printer.DriverName)"
Write-Host "Port:   $($printer.PortName)"
Write-Host "Status: $($printer.PrinterStatus)"
Write-Host ""
Write-Host "Server Printer JSON for this queue:"
Write-Host "{"
Write-Host "  `"kiosk1`": `"queue:$PrinterName`""
Write-Host "}"

try {
  Add-Type -AssemblyName System.Drawing
} catch {
  Fail "Could not load System.Drawing needed for a Windows driver test print. $($_.Exception.Message)"
}

$doc = New-Object System.Drawing.Printing.PrintDocument
$doc.PrinterSettings.PrinterName = $PrinterName
$doc.DocumentName = "Welcome System Printer Diagnostic"

if (-not $doc.PrinterSettings.IsValid) {
  Fail "Windows says printer '$PrinterName' is not valid for printing."
}

$doc.add_PrintPage({
  param($sender, $eventArgs)

  $titleFont = New-Object System.Drawing.Font("Arial", 16, [System.Drawing.FontStyle]::Bold)
  $bodyFont = New-Object System.Drawing.Font("Arial", 10, [System.Drawing.FontStyle]::Regular)
  $brush = [System.Drawing.Brushes]::Black

  $eventArgs.Graphics.DrawString("WELCOME SYSTEM", $titleFont, $brush, 20, 20)
  $eventArgs.Graphics.DrawString("Windows driver diagnostic print", $bodyFont, $brush, 20, 55)
  $eventArgs.Graphics.DrawString((Get-Date).ToString("yyyy-MM-dd HH:mm:ss"), $bodyFont, $brush, 20, 75)
  $eventArgs.Graphics.DrawString("If this does not print, fix Windows/printer setup before testing the app.", $bodyFont, $brush, 20, 95)
  $eventArgs.HasMorePages = $false
})

try {
  Write-Host ""
  Write-Host "Sending Windows driver test print..." -ForegroundColor Cyan
  $doc.Print()
} catch {
  Fail "Windows rejected the diagnostic print: $($_.Exception.Message)"
} finally {
  $doc.Dispose()
}

Write-Host "Windows accepted the diagnostic print job." -ForegroundColor Green
Write-Host ""
Write-Host "Watching the print queue for 20 seconds..."

for ($attempt = 1; $attempt -le 20; $attempt++) {
  Start-Sleep -Seconds 1
  $jobs = Get-PrintJob -PrinterName $PrinterName -ErrorAction SilentlyContinue
  if ($jobs) {
    $jobs | Format-Table ID, DocumentName, JobStatus, Size, SubmittedTime -AutoSize
  } else {
    Write-Host "No queued jobs visible."
  }
}

Write-Host ""
Write-Host "Diagnostic complete." -ForegroundColor Green
Write-Host "If the diagnostic page printed, use the queue JSON above in System Settings."
Write-Host "If it did not print, Windows accepted the job but the printer/driver did not produce output."
