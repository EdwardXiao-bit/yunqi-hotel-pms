$ErrorActionPreference = 'Stop'
$src = "C:\Users\Ed\dsh_workspace\database-course-project\docs\报告封面文档.doc"
$dstDocx = "C:\Users\Ed\dsh_workspace\database-course-project\work\cover.docx"
$dstPdf  = "C:\Users\Ed\dsh_workspace\database-course-project\work\cover.pdf"
New-Item -ItemType Directory -Force -Path "C:\Users\Ed\dsh_workspace\database-course-project\work" | Out-Null

$w = $null
try {
  $w = New-Object -ComObject Word.Application
  $w.Visible = $false
  $w.DisplayAlerts = 0
  $w.AutomationSecurity = 3
  $w.Options.ConfirmConversions = $false
  Start-Sleep -Milliseconds 500
  $doc = $w.Documents.Open($src, $false, $true, $false, "", "", $false, "", "", 0, 936, $false, $true, 0, $true)
  Write-Output "opened ok"
  $doc.SaveAs2($dstDocx, 16)
  $doc.SaveAs2($dstPdf, 17)
  $doc.Close(0)
  Write-Output "saved"
} catch {
  Write-Output ("ERR: " + $_.Exception.Message)
} finally {
  if ($w -ne $null) { try { $w.Quit(0) } catch {} }
}
