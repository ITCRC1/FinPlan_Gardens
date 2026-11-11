let
//#COMUN#
    // El P&L USALI tal como lo muestra el sistema (`/api/consolidado/propia/`),
    // una fila por linea, en el ORDEN del reporte. Arriba van las noches y los
    // huespedes de cada mes, que son la base del ADR y la ocupacion.
    //
    // ⚠️ `Annual` es el anual DEL SISTEMA, no siempre la suma de los meses: el
    // impuesto sobre la renta se recalcula sobre la utilidad del ANO. Si el ano
    // da perdida, el anual del impuesto es 0 aunque algun mes haya provisionado.
    // «Orden» va despues del nombre: la tercera columna es donde una version
    // que falla escribe su aviso, y en una columna numerica se perderia.
    Cols = {"Etiqueta","Version","Section","Line code","Line name","Orden"}
           & Meses & {"Annual","Leido"},

    Traer = (etiqueta as text, anio as text, tipoArg as text, versionArg as text) =>
        let r = Pedir("api/consolidado/propia/", anio, tipoArg, versionArg)
        in
            if r[Error] <> null then FalloEn(Cols, etiqueta, r[Error])
            else
                let
                    j = r[J],
                    ver = Txt(j[escenario][version]),
                    kpi = (campo as text, codigo as text, nombre as text, orden as number) =>
                        let serie = List.Transform(j[kpis_mes], each Num(Record.Field(_, campo)))
                        in {etiqueta, ver, "KPIS", codigo, nombre, orden} & serie
                           & {List.Sum(serie), Leido},
                    kpis = {kpi("rooms_available", "ROOMS_AVAILABLE", "Rooms available", 1),
                            kpi("rooms_occupied", "ROOMS_OCCUPIED", "Rooms occupied", 2),
                            kpi("guests", "GUESTS", "Guests", 3)},
                    lineas = List.Transform(List.Positions(j[lineas]), (i) =>
                        let l = j[lineas]{i}
                        in {etiqueta, ver, l[section], l[line_code], l[line_name], i + 4}
                           & List.Transform(l[meses], Num) & {Num(l[anual]), Leido})
                in
                    #table(Cols, kpis & lineas),

    Tabla = Apilar(Cols, Traer, {"Orden"} & Meses & {"Annual"})
in
    Tabla
