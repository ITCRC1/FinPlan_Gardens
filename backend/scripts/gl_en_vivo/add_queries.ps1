param([string]$In, [string]$Out, [string]$TestUrl = "", [string]$TestKey = "", [switch]$Probar)
# Mete las consultas de Power Query en el libro, via COM de Excel.
#
# Una consulta por hoja, y cada una lee la tabla `tVersiones` de Config y apila
# las versiones con una columna `Etiqueta`. Asi agregar un Draft es escribir un
# renglon en el libro, no editar la consulta ni volver a correr esto.
#
# Las hojas nuevas (2026-11-11: P&L, Posiciones, Planilla, OPEX) comparten el
# preambulo `_comun.m`, que se pega donde la consulta dice //#COMUN#.
#
# -Probar refresca SIN llave: cada version baja como «Falta la llave», pero
# Power Query tiene que compilar y correr cada consulta, asi que un error de
# sintaxis en el M aparece aca y no en la maquina del owner.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$comun = Get-Content -Raw -Encoding UTF8 (Join-Path $here "_comun.m")

function Leer-M([string]$archivo) {
    $txt = Get-Content -Raw -Encoding UTF8 (Join-Path $here $archivo)
    return $txt.Replace("//#COMUN#", $comun)
}

# (consulta, archivo .m, hoja, tabla, descripcion)
$consultas = @(
    @("GL",         "query.m",      "GL",         "tGL",         "Cuentas del mayor por mes, todas las versiones"),
    @("Escenarios", "escenarios.m", "Escenarios", "tEscenarios", "Escenarios y versiones disponibles"),
    @("PL",         "pl.m",         "P&L",        "tPL",         "P&L USALI por linea y mes"),
    @("Posiciones", "posiciones.m", "Posiciones", "tPosiciones", "Posiciones de planilla con FTE y costo"),
    @("Planilla",   "planilla.m",   "Planilla",   "tPlanilla",   "Checkbook de planilla: posicion x concepto x mes"),
    @("OPEX",       "opex.m",       "OPEX",       "tOPEX",       "Checkbook de OPEX: depto x cuenta x detalle x mes")
)

$xl = New-Object -ComObject Excel.Application
$xl.DisplayAlerts = $false
$xl.Visible = $false
try {
    $wb = $xl.Workbooks.Open($In)
    # Ignorar niveles de privacidad SOLO en este libro: la consulta combina
    # celdas del propio libro (llave, anio, version) con la web.
    $wb.Queries.FastCombine = $true
    if ($TestUrl) { $wb.Worksheets.Item("Config").Range("pURL").Value2 = $TestUrl }
    if ($TestKey) { $wb.Worksheets.Item("Config").Range("pLlave").Value2 = $TestKey }

    foreach ($c in $consultas) {
        $qn, $archivo, $hoja, $tabla, $desc = $c
        $m = if ($archivo -eq "query.m" -or $archivo -eq "escenarios.m") {
            Get-Content -Raw -Encoding UTF8 (Join-Path $here $archivo)
        } else { Leer-M $archivo }
        $wb.Queries.Add($qn, $m, "$desc, desde FinPlan Ojochal Gardens") | Out-Null

        $ws = $wb.Worksheets.Item($hoja)
        $ws.Cells.Clear() | Out-Null
        $conn = "OLEDB;Provider=Microsoft.Mashup.OleDb.1;Data Source=`$Workbook`$;Location=$qn;Extended Properties=`"`""
        $lo = $ws.ListObjects.Add(0, $conn, $null, 1, $ws.Range("A1"))
        $lo.Name = $tabla
        $qt = $lo.QueryTable
        $qt.CommandType = 2
        $qt.CommandText = "SELECT * FROM [$qn]"
        $qt.BackgroundQuery = $false
        $qt.RefreshStyle = 0      # xlOverwriteCells: no corre referencias
        $qt.PreserveColumnInfo = $true
        $qt.AdjustColumnWidth = $true
        if ($TestKey -or $Probar) {
            $qt.Refresh($false) | Out-Null
            Write-Host ("{0,-11} {1,6} filas" -f $qn, $lo.ListRows.Count)
        }
    }

    $wb.Worksheets.Item("Config").Activate()
    # La llave NO se guarda en el archivo que se comparte.
    $wb.Worksheets.Item("Config").Range("pLlave").Value2 = ""
    $wb.SaveAs($Out, 51)
    Write-Host "libro con consultas: $Out"
} finally {
    $wb = $null
    $xl.Quit()
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl)
}
