let
//#COMUN#
    // El checkbook de planilla: posicion × concepto (las 17 cuentas 6xxx) × mes,
    // en USD. Sale de la misma respuesta que la hoja Posiciones, abierta por
    // concepto. Van los 17 conceptos de cada posicion aunque esten en cero:
    // asi se ve como el checkbook, y un pivot por cuenta no pierde filas.
    Cols = {"Etiqueta","Version","Dept code","Department","Position code","Position",
            "Account","Concept","Group"}
           & Meses & {"Annual","Leido"},

    Traer = (etiqueta as text, anio as text, tipoArg as text, versionArg as text) =>
        let r = Pedir("api/consolidado/posiciones/", anio, tipoArg, versionArg)
        in
            if r[Error] <> null then FalloEn(Cols, etiqueta, r[Error])
            else
                let
                    j = r[J],
                    ver = Txt(j[escenario][version]),
                    filas = List.Combine(List.Transform(j[posiciones], (p) =>
                        List.Transform(j[conceptos], (c) =>
                            let serie = List.Transform(Record.Field(p[meses], c[key]), Num)
                            in {etiqueta, ver, p[dept], p[dept_name], p[codigo], p[puesto],
                                c[code], c[label], c[grupo]}
                               & serie & {List.Sum(serie), Leido})))
                in
                    if List.Count(filas) = 0
                    then FalloEn(Cols, etiqueta, "Este escenario no tiene posiciones")
                    else #table(Cols, filas),

    Tabla = Apilar(Cols, Traer, Meses & {"Annual"})
in
    Tabla
