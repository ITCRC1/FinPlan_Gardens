    // ── Preambulo comun de las hojas P&L, Posiciones, Planilla y OPEX ──────
    // `add_queries.ps1` lo pega donde cada consulta dice //#COMUN#. Una sola
    // copia: la tabla de versiones, la llave y el `*` se leen igual en todas,
    // y si cambia la forma de pedir, cambia en un lugar.
    P = (n as text) => Excel.CurrentWorkbook(){[Name = n]}[Content]{0}[Column1],
    Url = Text.Trim(Text.From(P("pURL"))),
    LlaveCruda = P("pLlave"),
    Llave = if LlaveCruda = null then "" else Text.Trim(Text.From(LlaveCruda)),

    TodasLasFilas = Excel.CurrentWorkbook(){[Name = "tVersiones"]}[Content],
    Versiones = Table.SelectRows(TodasLasFilas, each
        Text.Upper(Text.Trim(Text.From(Record.FieldOrDefault(_, "Usar", "SI")))) <> "NO"),

    Meses = {"M01","M02","M03","M04","M05","M06","M07","M08","M09","M10","M11","M12"},
    Num = (v) => if v = null then 0 else v,
    Txt = (v) => if v = null then "" else Text.From(v),
    Leido = DateTime.ToText(DateTime.LocalNow(), "dd/MM/yyyy HH:mm"),

    // Una version que falla baja como UNA fila que lo dice; las demas siguen.
    FalloEn = (cols as list, etiqueta as text, msg as text) =>
        #table(cols, {{etiqueta, "ERROR", msg} & List.Repeat({null}, List.Count(cols) - 3)}),

    // Pide una ruta del consolidado. Devuelve [Error = texto o null, J = json].
    // ⚠️ Los parametros NO se llaman igual que los campos del registro
    // (`[tipo = tipoArg]`): con el mismo nombre Power Query no los distingue.
    Pedir = (ruta as text, anio as text, tipoArg as text, versionArg as text) =>
        let
            Filtro = [year = anio, tipo = tipoArg]
                     & (if versionArg = "" then [] else [version = versionArg]),
            Resp = Web.Contents(Url, [
                RelativePath = ruta,
                Query = Filtro,
                Headers = [#"x-api-key" = Llave, Accept = "application/json"],
                ManualStatusHandling = {400, 404, 422, 500, 502, 503}
            ]),
            Estado = Value.Metadata(Resp)[Response.Status]
        in
            if Llave = "" then [Error = "Falta la llave de solo lectura en Config", J = null]
            else if Estado = 404 then
                [Error = "No existe " & tipoArg & " " & anio
                         & (if versionArg = "" then "" else " version '" & versionArg & "'"), J = null]
            else if Estado <> 200 then [Error = "El servidor respondio HTTP " & Text.From(Estado), J = null]
            else [Error = null, J = Json.Document(Resp)],

    // `*` en Version -> todas las versiones de ese anio y tipo (igual que el GL).
    ListaEscenarios =
        let
            R = Web.Contents(Url, [
                RelativePath = "api/consolidado/escenarios/",
                Headers = [#"x-api-key" = Llave, Accept = "application/json"],
                ManualStatusHandling = {400, 404, 422, 500, 502, 503}
            ])
        in
            if Llave = "" or Value.Metadata(R)[Response.Status] <> 200
            then {}
            else Json.Document(R)[escenarios],

    Abrir = (fila as record) as list =>
        let
            anio = Text.From(fila[Anio]),
            tipo = Text.Upper(Text.From(fila[Tipo])),
            etq = Text.From(fila[Etiqueta]),
            crudo = let v = fila[Version] in if v = null then "" else Text.Trim(Text.From(v))
        in
            if crudo <> "*" then {[E = etq, A = anio, T = tipo, V = crudo]}
            else
                let
                    hay = List.Select(ListaEscenarios, each
                        Text.From([year]) = anio and Text.Upper(Text.From([tipo])) = tipo),
                    nombres = List.Distinct(List.Transform(hay, each Txt([version])))
                in
                    if List.Count(nombres) = 0
                    then {[E = etq, A = anio, T = tipo, V = ""]}
                    else List.Transform(nombres, (v) =>
                        [E = etq & " · " & (if v = "" then "(sin version)" else v),
                         A = anio, T = tipo, V = v]),

    Expandidas = Table.FromRecords(List.Combine(
        Table.TransformRows(Versiones, each Abrir(_)))),

    // Apila lo que devuelve `traer` para cada version prendida.
    Apilar = (cols as list, traer as function, numericas as list) =>
        let
            ConDatos = Table.AddColumn(Expandidas, "Datos", each traer([E], [A], [T], [V])),
            Unido = Table.ExpandTableColumn(Table.SelectColumns(ConDatos, {"Datos"}), "Datos", cols)
        in
            Table.TransformColumnTypes(Unido, List.Transform(numericas, each {_, type number})),
