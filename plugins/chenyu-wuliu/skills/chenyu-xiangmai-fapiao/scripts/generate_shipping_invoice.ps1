param(
  [Parameter(Mandatory = $true)][string]$InputPath,
  [Parameter(Mandatory = $true)][string]$OutputPath,
  [string]$TemplatePath
)

$ErrorActionPreference = 'Stop'
$issues = [System.Collections.Generic.List[string]]::new()
$warnings = [System.Collections.Generic.List[string]]::new()

function Txt($value) {
  if ($null -eq $value) { return '' }
  return ([string]$value).Trim()
}
function Need($value, [string]$label) {
  if (-not (Txt $value)) { [void]$script:issues.Add("${label}：缺失") }
}
function Need-Positive($value, [string]$label) {
  if ($value -isnot [System.ValueType] -or $value -is [bool] -or [double]$value -le 0) {
    [void]$script:issues.Add("${label}：必须为正数")
  }
}
function Need-Flag($value, [string]$label) {
  if ($value -isnot [bool]) { [void]$script:issues.Add("${label}：须确认是或否") }
}
function Yes-No($value) {
  if ($value -eq $true) { return '是' }
  if ($value -eq $false) { return '否' }
  return ''
}
function Put($sheet, [string]$address, $value, [switch]$PreserveText) {
  if ($null -eq $value -or (Txt $value) -eq '') { return }
  $cell = $sheet.Range($address)
  if ($cell.HasFormula) { throw "模板公式不可覆盖：$address" }
  if ($PreserveText) { $cell.Value2 = "'" + [string]$value }
  elseif ($value -is [System.ValueType]) { $cell.Value2 = [double]$value }
  else { $cell.Value2 = [string]$value }
}
function Check-Lookup($sheet, [string]$address) {
  $cell = $sheet.Range($address)
  if (-not $cell.HasFormula) { throw "模板公式缺失：$address" }
  $value = Txt $cell.Text
  if (-not $value -or $value.StartsWith('#')) { throw "地址库编码未能带出 $address；请核对本次仓库地址编码" }
}

$inputFull = [System.IO.Path]::GetFullPath($InputPath)
if (-not (Test-Path -LiteralPath $inputFull -PathType Leaf)) { throw "输入 JSON 不存在：$inputFull" }
$data = Get-Content -LiteralPath $inputFull -Raw -Encoding UTF8 | ConvertFrom-Json -Depth 30
$carrier = Txt $data.carrier
$shipment = $data.shipment
$recipient = $shipment.recipient
$boxes = if ($null -eq $data.cartons) { @() } else { @($data.cartons) }
if ($carrier -notin @('lianhang', 'yiluda')) { [void]$issues.Add('carrier：必须为 lianhang 或 yiluda') }
Need $shipment.service '服务/渠道'
Need $shipment.addressCode '仓库地址编码'
Need $shipment.declarationMode '报关方式'
foreach ($pair in @(@('battery','带电'),@('magnet','带磁'),@('liquid','液体'),@('powder','粉末'),@('dangerous','危险品'))) {
  Need-Flag $shipment.flags.($pair[0]) $pair[1]
}
if ($carrier -eq 'yiluda') {
  Need $shipment.customerOrderNo '客户订单号'
  Need $shipment.taxMode '交税方式'
  Need $shipment.currency '申报币种'
  Need-Flag $shipment.flags.wood '木制品'
  Need-Flag $shipment.flags.textile '纺织品'
  Need-Flag $shipment.insurance '是否购买保险'
}
if ($boxes.Count -eq 0) { [void]$issues.Add('cartons：至少需要一箱') }
$seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
$itemRows = 0
for ($ci = 0; $ci -lt $boxes.Count; $ci++) {
  $box = $boxes[$ci]
  $boxLabel = "第$($ci + 1)箱"
  Need $box.cartonNo "$boxLabel FBA箱号"
  if ((Txt $box.cartonNo) -and -not $seen.Add((Txt $box.cartonNo))) { [void]$issues.Add("$boxLabel FBA箱号：重复") }
  Need-Positive $box.weightKg "$boxLabel 箱重kg"
  if ($null -eq $box.dimensionsCm -or @($box.dimensionsCm).Count -ne 3) {
    [void]$issues.Add("$boxLabel 尺寸：需要长宽高三个数")
  } else {
    for ($d = 0; $d -lt 3; $d++) { Need-Positive $box.dimensionsCm[$d] "$boxLabel 尺寸第$($d + 1)项cm" }
  }
  $items = if ($null -eq $box.items) { @() } else { @($box.items) }
  if ($items.Count -eq 0) { [void]$issues.Add("$boxLabel：至少需要一款商品") }
  for ($ii = 0; $ii -lt $items.Count; $ii++) {
    $item = $items[$ii]
    $itemRows++
    $label = "$boxLabel 第$($ii + 1)款"
    if (-not (Txt $item.msku) -and -not (Txt $item.sku)) { [void]$issues.Add("$label：缺少领星 SKU/MSKU 匹配依据") }
    Need $item.nameZh "$label 中文品名"
    Need $item.nameEn "$label 英文品名"
    if (($item.quantity -isnot [int] -and $item.quantity -isnot [long]) -or $item.quantity -le 0) { [void]$issues.Add("$label 单箱数量：必须为正整数") }
    Need-Positive $item.declaredUnitPrice "$label 申报单价"
    Need $item.material "$label 材质"
    if ((Txt $item.hsCode) -notmatch '^[0-9]{6,12}$') { [void]$issues.Add("$label 海关编码：需要已确认的6到12位数字文本") }
    if ($carrier -eq 'lianhang') {
      Need $item.purpose "$label 用途"
      Need $item.brand "$label 品牌（无品牌写无）"
      Need $item.model "$label 型号（无型号写无）"
    }
    if (-not (Txt $item.salesUrl)) { [void]$warnings.Add("$label：领星未提供稳定销售链接，发票留空") }
    if (-not (Txt $item.imageUrl)) { [void]$warnings.Add("$label：领星未提供稳定图片链接，发票留空") }
  }
}
$capacity = if ($carrier -eq 'lianhang') { 33 } else { 28 }
if ($itemRows -gt $capacity) { [void]$issues.Add("商品行数 $itemRows 超出原模板已格式化的 $capacity 行；不扩展模板") }
if ($issues.Count -gt 0) {
  [PSCustomObject]@{ status = 'blocked'; issues = @($issues) } | ConvertTo-Json -Depth 5
  exit 2
}

if (-not $TemplatePath) {
  $asset = if ($carrier -eq 'lianhang') { 'lianhang-template.xls' } else { 'yiluda-template.xls' }
  $TemplatePath = Join-Path (Join-Path $PSScriptRoot '..\assets') $asset
}
$templateFull = [System.IO.Path]::GetFullPath($TemplatePath)
$outputFull = [System.IO.Path]::GetFullPath($OutputPath)
if ($outputFull -ieq $templateFull -or $outputFull -ieq $inputFull) { throw '输出路径不能覆盖输入或原模板' }
if (-not $outputFull.EndsWith('.xls', [System.StringComparison]::OrdinalIgnoreCase)) { throw '为保持原模板格式，输出必须为 .xls' }
if (-not (Test-Path -LiteralPath $templateFull -PathType Leaf)) { throw "原模板不存在：$templateFull" }
if (Test-Path -LiteralPath $outputFull) { throw "输出文件已存在，拒绝覆盖：$outputFull" }
$outputDir = [System.IO.Path]::GetDirectoryName($outputFull)
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
$staging = Join-Path $outputDir ('.building-' + [guid]::NewGuid().ToString('N') + '.xls')
Copy-Item -LiteralPath $templateFull -Destination $staging

$wps = $null
$book = $null
try {
  $wps = New-Object -ComObject ket.Application
  $wps.Visible = $false
  $wps.DisplayAlerts = $false
  $book = $wps.Workbooks.Open($staging, 0, $false)
  if ($book.FileFormat -ne 56) { throw '模板不是原始 Excel 97-2003 .xls 格式' }
  $sheetName = if ($carrier -eq 'lianhang') { '模板' } else { '发票模板' }
  $sheet = $book.Worksheets.Item($sheetName)
  $firstRow = if ($carrier -eq 'lianhang') { 19 } else { 18 }
  $lastCol = if ($carrier -eq 'lianhang') { 'U' } else { 'S' }
  $headerRow = $firstRow - 1
  if ((Txt $sheet.Range("A$headerRow").Value2) -ne '货箱编号*') { throw '模板货箱编号表头不匹配' }
  foreach ($cell in $sheet.Range("A${firstRow}:${lastCol}$($firstRow + $capacity - 1)").Cells) {
    if ($cell.HasFormula -or $null -ne $cell.Value2) { throw '空白模板数据区含旧货件或公式，拒绝生成' }
  }
  if ($carrier -eq 'lianhang') {
    Put $sheet 'B1' (Txt $shipment.customerOrderNo)
    Put $sheet 'B2' (Txt $shipment.service)
    Put $sheet 'B3' (Txt $shipment.addressCode)
    Put $sheet 'B5' (Txt $recipient.company)
    Put $sheet 'B7' (Txt $recipient.address2)
    Put $sheet 'B8' (Txt $recipient.address3)
    Put $sheet 'B14' (Txt $recipient.email)
    Put $sheet 'B15' (Txt $shipment.poNumber)
    Put $sheet 'B16' $boxes.Count
    Put $sheet 'B17' (Txt $shipment.remarks)
    $flags = @($shipment.flags.battery,$shipment.flags.magnet,$shipment.flags.liquid,$shipment.flags.powder,$shipment.flags.dangerous)
    for ($i = 0; $i -lt 5; $i++) { Put $sheet "F$($i + 1)" (Yes-No $flags[$i]) }
    $right = @($shipment.declarationMode,$shipment.customsMode,$shipment.taxMode,$shipment.incoterm,$shipment.deliveryMode,$shipment.vatNo,$shipment.eoriNo,$shipment.reference1,$shipment.reference2)
    for ($i = 0; $i -lt $right.Count; $i++) { Put $sheet "F$($i + 6)" (Txt $right[$i]) }
    if ($shipment.insurance -is [bool]) { Put $sheet 'F15' (Yes-No $shipment.insurance) }
    Put $sheet 'F16' $shipment.insuredAmount
    Put $sheet 'F17' (Txt $shipment.currency)
    Put $sheet 'J1' (Txt $shipment.store)
    $sender = $shipment.sender
    $senderValues = @($sender.addressCode,$sender.name,$sender.company,$sender.address1,$sender.address2,$sender.address3,$sender.city,$sender.province,$sender.postalCode,$sender.countryCode,$sender.phone,$sender.email)
    for ($i = 0; $i -lt $senderValues.Count; $i++) { Put $sheet "J$($i + 2)" (Txt $senderValues[$i]) }
  } else {
    Put $sheet 'B1' (Txt $shipment.customerOrderNo)
    Put $sheet 'B2' (Txt $shipment.service)
    Put $sheet 'B3' (Txt $shipment.addressCode)
    Put $sheet 'B12' (Txt $recipient.email)
    Put $sheet 'B13' (Txt $shipment.taxMode)
    Put $sheet 'B14' $boxes.Count
    Put $sheet 'B15' (Txt $shipment.declarationMode)
    Put $sheet 'B16' (Txt $shipment.customsMode)
    $flags = @($shipment.flags.battery,$shipment.flags.magnet,$shipment.flags.liquid,$shipment.flags.powder,$shipment.flags.dangerous,$shipment.flags.wood,$shipment.flags.textile)
    for ($i = 0; $i -lt 7; $i++) { Put $sheet "F$($i + 1)" (Yes-No $flags[$i]) }
    Put $sheet 'F8' (Yes-No $shipment.insurance)
    Put $sheet 'F9' (Txt $shipment.currency)
    $right = @($shipment.vatNo,$shipment.eoriNo,$shipment.registeredCompany,$shipment.registeredAddress,$shipment.insuredAmount,$shipment.remarks,$shipment.storeUrl)
    for ($i = 0; $i -lt $right.Count; $i++) { Put $sheet "F$($i + 10)" $right[$i] }
  }

  $row = $firstRow
  foreach ($box in $boxes) {
    $items = @($box.items)
    for ($ii = 0; $ii -lt $items.Count; $ii++) {
      $item = $items[$ii]
      if ($ii -eq 0) {
        Put $sheet "A$row" (Txt $box.cartonNo)
        if ($carrier -eq 'lianhang') {
          $boxColumns = @('B','C','D','E')
          $boxValues = @($box.weightKg,$box.dimensionsCm[0],$box.dimensionsCm[1],$box.dimensionsCm[2])
        } else {
          $boxColumns = @('B','C','D','E','F')
          $boxValues = @(1,$box.weightKg,$box.dimensionsCm[0],$box.dimensionsCm[1],$box.dimensionsCm[2])
        }
        for ($c = 0; $c -lt $boxColumns.Count; $c++) { Put $sheet "$($boxColumns[$c])$row" ([double]$boxValues[$c]) }
      }
      if ($carrier -eq 'lianhang') {
        $columns = @('F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U')
        $sku = if (Txt $item.sku) { Txt $item.sku } else { Txt $item.msku }
        $values = @($item.nameEn,$item.nameZh,$item.declaredUnitPrice,$item.quantity,$item.material,$item.hsCode,$item.purpose,$item.brand,$item.model,$item.salesUrl,$item.salePrice,$item.imageUrl,$item.productWeightKg,$item.asin,$item.fnsku,$sku)
      } else {
        $columns = @('G','H','I','J','K','L','M','N','O','P','Q','R','S')
        $po = if (Txt $item.poNumber) { Txt $item.poNumber } else { Txt $shipment.poNumber }
        $values = @($item.nameZh,$item.nameEn,$item.declaredUnitPrice,$item.quantity,$item.material,$item.hsCode,$item.purpose,$item.brand,$item.brandType,$item.model,$item.salesUrl,$item.imageUrl,$po)
      }
      $hsColumn = if ($carrier -eq 'lianhang') { 'K' } else { 'L' }
      for ($c = 0; $c -lt $columns.Count; $c++) {
        if ($columns[$c] -eq $hsColumn) { Put $sheet "$($columns[$c])$row" $values[$c] -PreserveText }
        else { Put $sheet "$($columns[$c])$row" $values[$c] }
      }
      $row++
    }
  }
  $wps.CalculateFull()
  if ($carrier -eq 'lianhang') {
    foreach ($address in @('B4','B6','B9','B11','B12')) { Check-Lookup $sheet $address }
    $postalCell = 'B11'; $countryCell = 'B12'
  } else {
    foreach ($address in @('B4','B5','B6','B7','B9','B10')) { Check-Lookup $sheet $address }
    $postalCell = 'B9'; $countryCell = 'B10'
  }
  if ((Txt $recipient.postalCode) -and (Txt $recipient.postalCode) -ne (Txt $sheet.Range($postalCell).Value2)) { throw '本次收件邮编与模板地址库结果不一致' }
  if ((Txt $recipient.countryCode) -and (Txt $recipient.countryCode).ToUpperInvariant() -ne (Txt $sheet.Range($countryCell).Value2).ToUpperInvariant()) { throw '本次收件国家与模板地址库结果不一致' }
  $book.Save()
  $book.Close($false)
  [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($book)
  $book = $null
  Move-Item -LiteralPath $staging -Destination $outputFull
  [PSCustomObject]@{ status = 'created'; output = $outputFull; carrier = $carrier; cartons = $boxes.Count; itemRows = $itemRows; warnings = @($warnings) } | ConvertTo-Json -Depth 5
} finally {
  if ($null -ne $book) { $book.Close($false); [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($book) }
  if ($null -ne $wps) { $wps.Quit(); [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($wps) }
  if (Test-Path -LiteralPath $staging -PathType Leaf) { Remove-Item -LiteralPath $staging -Force }
}
