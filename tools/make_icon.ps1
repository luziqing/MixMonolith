Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap 96, 96
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.Clear([System.Drawing.Color]::FromArgb(10, 14, 20))
$pen1 = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(0, 230, 255))
$pen2 = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(120, 0, 220))
for ($i = 0; $i -lt 4; $i++) {
    $d = 14 + $i * 20
    $p = if ($i % 2 -eq 0) { $pen1 } else { $pen2 }
    $g.DrawEllipse($p, (96 - $d) / 2, (96 - $d) / 2, $d, $d)
}
$g.FillEllipse([System.Drawing.Brush]$pen1.Brush, 44, 44, 8, 8)
$font = New-Object System.Drawing.Font('Consolas', 11, [System.Drawing.FontStyle]::Bold)
$g.DrawString('HP', $font, [System.Drawing.Brushes]::White, 22, 76)
$bmp.Save('C:\docker\HPpad\app\src\HpScope\res\drawable\ic.png', [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Output 'icon written'
