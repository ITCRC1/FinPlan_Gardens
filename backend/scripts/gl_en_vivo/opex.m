let
//#COMUN#
    // El checkbook de OPEX (clase 7): depto × cuenta × detalle × mes, en USD
    // (`/api/consolidado/opex/`). Si la linea es en colones, los meses son los
    // dolares derivados con el TC de cada mes y `CRC annual` trae los colones.
    // No trae el reparto que le cae a un depto: eso no es una linea del checkbook.
    Cols = {"Etiqueta","Version","Dept code","Department","Account","Account name",
            "Detail","Detail description","Currency"}
           & Meses & {"Annual","CRC annual","Leido"},

    Traer = (etiqueta as text, anio as text, tipoArg as text, versionArg as text) =>
        let r = Pedir("api/consolidado/opex/", anio, tipoArg, versionArg)
        in
            if r[Error] <> null then FalloEn(Cols, etiqueta, r[Error])
            else
                let
                    j = r[J],
                    ver = Txt(j[escenario][version]),
                    filas = List.Transform(j[lineas], each
                        {etiqueta, ver, [dept], [dept_name], [cuenta], [nombre],
                         [detalle], [detalle_desc], [moneda]}
                        & List.Transform([meses], Num)
                        & {Num([anual]), Num([crc_anual]), Leido})
                in
                    if List.Count(filas) = 0
                    then FalloEn(Cols, etiqueta, "Este escenario no tiene lineas de OPEX")
                    else #table(Cols, filas),

    Tabla = Apilar(Cols, Traer, Meses & {"Annual","CRC annual"})
in
    Tabla
