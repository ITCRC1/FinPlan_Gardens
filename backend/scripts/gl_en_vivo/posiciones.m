let
//#COMUN#
    // Una fila por posicion: puesto, salario, FTE de cada mes y lo que cuesta en
    // el ano (`/api/consolidado/posiciones/`, el mismo armado que el reporte
    // «Planilla por posicion»). Sin el nombre de la persona, a proposito.
    FteCols = List.Transform(Meses, each "FTE " & _),
    Cols = {"Etiqueta","Version","Dept code","Department","Position code","Position",
            "Salary currency","Salary"}
           & FteCols & {"FTE avg","Devengado","Cargas","Beneficios","Annual cost","Leido"},

    Traer = (etiqueta as text, anio as text, tipoArg as text, versionArg as text) =>
        let r = Pedir("api/consolidado/posiciones/", anio, tipoArg, versionArg)
        in
            if r[Error] <> null then FalloEn(Cols, etiqueta, r[Error])
            else
                let
                    j = r[J],
                    ver = Txt(j[escenario][version]),
                    filas = List.Transform(j[posiciones], each
                        {etiqueta, ver, [dept], [dept_name], [codigo], [puesto],
                         [moneda_salario], Num([salario])}
                        & List.Transform([fte], Num)
                        & {Num([fte_prom]), Num([devengado]), Num([cargas]),
                           Num([beneficios]), Num([costo]), Leido})
                in
                    if List.Count(filas) = 0
                    then FalloEn(Cols, etiqueta, "Este escenario no tiene posiciones")
                    else #table(Cols, filas),

    Tabla = Apilar(Cols, Traer,
                   {"Salary"} & FteCols & {"FTE avg","Devengado","Cargas","Beneficios","Annual cost"})
in
    Tabla
