"""
Siembra el motor de mapeo del P&L: `report_line_config` + `account_mapping`.

POR QUÉ EXISTE
Estas 899 filas son las que traducen el catálogo contable a las líneas del P&L
USALI. Sin ellas el motor corre y devuelve todo en cero: no es una tabla de
adorno, es el corazón del cálculo. Vivían SOLO en la base de Corcovado, así que
una instalación nueva —cada hotel va a ser un proyecto aparte— nacía muerta y
había que copiarle la base al anterior. Ahora viven en git.

No dependen del hotel: son el estándar USALI, iguales para Corcovado, Amarena,
Oxígen y Ojochal. Por eso no llevan `hotel_id`.

IDEMPOTENTE Y NO DESTRUCTIVO
Inserta lo que falta y actualiza lo que cambió; NO borra lo que sobra. Un hotel
puede haber agregado mapeos propios y el seed corre en cada arranque: borrar por
ausencia le vaciaría el P&L a alguien en un redeploy. Lo que sobra se reporta
para que se mire, no se toca.
"""
import json
import pathlib
import uuid

from sqlalchemy import UniqueConstraint, select
from app.models.mapping import ReportLineConfig, AccountMapping

ARCHIVO = pathlib.Path(__file__).parent / "seed_data" / "mapping_pl.json"

# ⚠️ La clave se DERIVA de la restricción de la tabla, no se escribe acá.
#
# Hasta el 2026-08-20 estaban escritas a mano, y decían ser «las mismas de las
# restricciones» sin serlo: a `uq_account_mapping` se le agregó `vigente_desde`
# —la vigencia que D9 necesitó para mover la 7120— y esta clave se quedó con
# cuatro columnas. Resultado: las dos reglas de la 7120 (hasta jun-2026 en A&G,
# desde jul-2026 en Credit Card Commissions) se veían como UNA, el seed
# intentaba insertar la segunda, y **la siembra del mapeo se caía entera en cada
# despliegue** con un `IntegrityError` que el `try/except` convertía en una
# línea de log. Todo el lote se revertía con ella.
#
# Derivada, la clave no puede volver a separarse de la restricción.
def _columnas_unicas(modelo) -> tuple[str, ...]:
    for c in modelo.__table__.constraints:
        if isinstance(c, UniqueConstraint):
            return tuple(col.name for col in c.columns)
    raise RuntimeError(f"{modelo.__name__} no tiene restricción única: sin ella "
                       f"el seed no puede saber qué fila es cuál")


def _clave(modelo):
    cols = _columnas_unicas(modelo)

    def clave(r) -> tuple:
        # `None` y `""` son lo mismo acá: el archivo omite la columna y la base
        # guarda NULL. Tratarlos distinto haría que cada fila sin vigencia se
        # viera como nueva en cada arranque.
        return tuple((r.get(c) if isinstance(r, dict) else getattr(r, c, None)) or None
                     for c in cols)
    return clave


_clave_linea = _clave(ReportLineConfig)
_clave_mapeo = _clave(AccountMapping)

#: Las columnas del índice único PARCIAL que la migración 123 creó sobre
#: `account_mapping`, y que la clave de arriba NO cubre:
#:
#:     CREATE UNIQUE INDEX uq_mapping_activo_depto_cuenta
#:     ON account_mapping (report_id, dept_code, account_code,
#:                         COALESCE(vigente_desde,''), COALESCE(vigente_hasta,''))
#:     WHERE active_status = 'YES'
#:
#: ⚠️ Mira `dept_code`; la clave de negocio mira `source_department` y además
#: `source_origin`. Son columnas DISTINTAS, así que dos filas pueden ser
#: «distintas» para el seed y «la misma» para la base.
_COLS_INDICE_PARCIAL = ("report_id", "dept_code", "account_code",
                        "vigente_desde", "vigente_hasta")


def _clave_ocupada_mapeo(r) -> tuple | None:
    """La ranura que esta fila ocupa en el índice parcial, o `None` si no aplica.

    **Por qué existe** (2026-11-02). El 2026-09-09 se le cambió el `source_origin`
    a la regla del 7310 de Tours —de `Revenue` a `Payroll`, que es lo correcto:
    es una cuenta de gasto—. Pero `source_origin` ES parte de la clave de negocio
    y NO es parte del índice, así que el seed veía una fila nueva, la insertaba,
    y Postgres la rechazaba porque la ranura (report, 0150, 7310) ya estaba
    tomada por la vieja.

    `seed_mapping` confirma UNA sola vez, al final de las dos siembras. Esa
    excepción reventaba el `commit` y **revertía el lote entero**: las 1.150
    reglas y las 123 líneas del reporte, en cada despliegue, desde septiembre.
    El arranque lo atrapaba y lo dejaba en una línea de log —«seed de mapeo
    omitido: …»— y seguía como si nada.

    Lo que costó: las cuatro líneas de Rent (`REV_RENT`, `OPEX_RENT`,
    `COS_RENT`, `PROFIT_RENT`) nunca entraron a `report_line_config`, así que
    el alquiler de locales sumaba a `TOTAL_REVENUES` y no se dibujaba en
    ninguna fila; y **ningún cambio de mapeo se podía aplicar**, ni siquiera
    para revertir otro.

    Con esto el seed ADOPTA la fila que ya ocupa la ranura y le re-afirma los
    campos, en vez de insertar una gemela que la base va a rechazar.
    """
    g = (lambda c: (r.get(c) if isinstance(r, dict) else getattr(r, c, None)))
    if str(g("active_status") or "").upper() != "YES":
        return None   # el índice es parcial: sólo rige sobre las activas
    return tuple((g(c) or "").strip() for c in _COLS_INDICE_PARCIAL)


def _campos(obj) -> dict:
    """Columnas del modelo salvo el id, que es por instalación."""
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns if c.name != "id"}


async def _sembrar(session, modelo, filas: list[dict], clave, nombre: str,
                   ocupada=None) -> None:
    """Siembra `filas` en `modelo`. `ocupada` es la clave del índice parcial.

    Ver `_clave_ocupada_mapeo`: sin ella, una fila que el seed ve como nueva y
    la base ve como repetida tumba el `commit` y revierte TODO el lote.
    """
    objetos = (await session.execute(select(modelo))).scalars().all()
    existentes = {clave(_campos(o)): o for o in objetos}
    ranuras: dict[tuple, object] = {}
    if ocupada is not None:
        for o in objetos:
            k = ocupada(_campos(o))
            if k is not None:
                ranuras.setdefault(k, o)

    nuevos = cambiados = adoptadas = 0
    for fila in filas:
        actual = existentes.pop(clave(fila), None)
        if actual is None and ocupada is not None:
            k = ocupada(fila)
            # La ranura está tomada por otra fila: es LA MISMA para la base.
            # Adoptarla y re-afirmarle los campos; insertar sería un 23505 que
            # se lleva puesto el lote entero.
            tomada = ranuras.get(k) if k is not None else None
            if tomada is not None:
                existentes.pop(clave(_campos(tomada)), None)
                actual, adoptadas = tomada, adoptadas + 1
        if actual is None:
            nueva = modelo(id=str(uuid.uuid4()), **fila)
            if ocupada is not None:
                k = ocupada(fila)
                if k is not None:
                    ranuras[k] = nueva
            session.add(nueva)
            nuevos += 1
            continue
        difs = [k for k, v in fila.items() if getattr(actual, k) != v]
        if difs:
            for k in difs:
                setattr(actual, k, fila[k])
            cambiados += 1
    sobran = len(existentes)
    print(f"  {nombre}: +{nuevos} nuevos, {cambiados} actualizados, {len(filas)} en el archivo"
          + (f", {adoptadas} adoptadas (ya ocupaban su ranura)" if adoptadas else "")
          + (f" · {sobran} en la base que NO están en el archivo (no se tocan)" if sobran else ""))


async def seed_mapping(session) -> None:
    if not ARCHIVO.exists():
        print(f"  seed de mapeo omitido: falta {ARCHIVO.name}")
        return
    datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    await _sembrar(session, ReportLineConfig, datos["report_line_config"], _clave_linea,
                   "report_line_config")
    await _sembrar(session, AccountMapping, datos["account_mapping"], _clave_mapeo,
                   "account_mapping", ocupada=_clave_ocupada_mapeo)
    await session.commit()
