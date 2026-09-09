# -*- coding: utf-8 -*-
"""La semilla de Break-Even de ESTA propiedad cubre todo su gasto.

## Qué cuida, y por qué no se ve si falla

El motor del equilibrio resuelve cada monto del P&L por `(dept_code, account)`;
si no encuentra regla, el monto **entra igual** al cálculo como **100% fijo** y
queda anotado en «Por defecto: 100% fijo» (`engine/break_even.py`, §2.6). O sea
que una cuenta sin clasificar **no da error, no da cero y no rompe el cuadre**:
solo mueve el equilibrio hacia arriba y el margen de contribución hacia abajo,
en una pantalla que sigue sumando bien. Es exactamente el tipo de error que este
módulo existe para no volver a cometer.

Con la semilla vacía pasa lo mismo pero al revés y en grande: el tab sale con
**100% de margen de contribución**, que es la firma de «no hay clasificación
cargada» y se lee como «este hotel no tiene costo variable».

Por eso la prueba no compara números: comprueba que **toda cuenta de gasto de
`orden_plantilla.json` que caiga en un departamento ACTIVO tenga su regla**, o
esté declarada acá abajo con su motivo. Si mañana alguien agrega una cuenta al
catálogo y no la clasifica, esta prueba falla y le dice cuál.

## La lista de exclusiones es una declaración, no un colador

`SIN_CLASIFICAR_A_PROPOSITO` se verifica en los dos sentidos: una cuenta
declarada acá que **sí** esté en la semilla también hace fallar la prueba. Una
lista que solo perdona nunca se limpia.
"""
import csv
import json
import pathlib

import pytest

from app.hotel_actual import HOTEL_ID
from app.models.break_even import DEPT_ACTIVO

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SEMILLAS = RAIZ / "app" / "seed_data"
CARPETA = SEMILLAS / HOTEL_ID / "break_even"

#: Cuentas de gasto de `orden_plantilla.json` que quedan **fuera** de la semilla
#: a propósito, con el motivo. El motor las va a tratar como 100% fijo, que es
#: el criterio conservador: asumirlas variables inflaría el margen y bajaría el
#: equilibrio — el error que se ve como buena noticia.
#:
#: `(dept_code, cuenta): motivo`
SIN_CLASIFICAR_A_PROPOSITO = {
    ("0140", "5300"): (
        "Spa Retail 1 Cost — costo de venta del retail del Spa. CWL no lo "
        "clasifica en ningún departamento y su bloque no es unánime: los "
        "COST OF SALES de CWL son variables salvo el de Transportation "
        "(renting/transfers), que es fijo. Falta que el owner confirme si el "
        "Spa de Ojochal vende retail y si ese costo sigue a la venta."),
    ("0140", "5301"): (
        "Spa Retail 2 Cost — el mismo caso que la 5300. CWL sí clasifica la "
        "5301, pero en Lavandería (0162), que es un costo de reparto y no de "
        "venta: la analogía cruzaría de un departamento de soporte a uno "
        "operativo, y en CWL la naturaleza del departamento manda sobre el "
        "código de cuenta."),
}


def _leer(nombre: str) -> list[dict]:
    """SIEMPRE utf-8 explícito: los nombres traen «Á», «&» y «·», y en Windows
    el default es cp1252 — entrarían corruptos y el apareo por nombre fallaría
    en silencio, que es peor que fallar."""
    with (CARPETA / nombre).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def deptos() -> list[dict]:
    return _leer("be_departments_seed.csv")


@pytest.fixture(scope="module")
def clases() -> list[dict]:
    return _leer("be_classification_seed.csv")


@pytest.fixture(scope="module")
def gasto_del_catalogo() -> list[tuple[str, str]]:
    """Las cuentas de GASTO de la plantilla: todo lo que no es `Revenue`."""
    datos = json.loads(
        (SEMILLAS / "orden_plantilla.json").read_text(encoding="utf-8"))
    return [(r["dept_code"], r["cuenta"]) for r in datos["orden"]
            if r["clase"] != "Revenue"]


def test_la_propiedad_trae_su_semilla():
    """Sin carpeta propia, el hotel nace sin clasificación — y eso no da error:
    el tab muestra 100% de margen de contribución. Ver `app/seed_break_even.py`.
    """
    assert CARPETA.is_dir(), (
        f"{HOTEL_ID} no tiene semilla de break-even en {CARPETA}. Una "
        f"propiedad sin carpeta NO hereda la de otra: nace sin clasificar.")
    for nombre in ("be_departments_seed.csv", "be_classification_seed.csv"):
        assert (CARPETA / nombre).is_file(), f"falta {nombre} en {CARPETA}"


def test_la_semilla_es_coherente():
    """La misma verificación que hace el arranque, corrida en la prueba: sin
    departamentos huérfanos y sin llaves repetidas. Que reviente acá y no en un
    despliegue."""
    from app.seed_break_even import leer

    d, c = leer(HOTEL_ID)
    assert d and c


def test_toda_cuenta_de_gasto_tiene_regla(deptos, clases, gasto_del_catalogo):
    """El corazón de la prueba.

    Se mide solo contra los departamentos **activos**: los que la propiedad no
    opera quedan en `pending_classification` y su gasto —si algún día llega—
    cae en «Por defecto: 100% fijo», que es lo que corresponde para un
    departamento del que no se sabe nada todavía.
    """
    activos = {c.strip(): d["slug"] for d in deptos
               if d["status"] == DEPT_ACTIVO
               for c in d["dept_codes"].split(",") if c.strip()}
    con_regla = {(c["dept_code"], c["account"]) for c in clases if c["account"]}

    faltan = sorted(
        par for par in set(gasto_del_catalogo)
        if par[0] in activos
        and par not in con_regla
        and par not in SIN_CLASIFICAR_A_PROPOSITO)
    assert not faltan, (
        "cuentas de gasto sin clasificar y sin declarar. El motor las va a "
        "contar como 100% fijo y NADIE se va a enterar: agregalas a "
        f"{CARPETA / 'be_classification_seed.csv'} o declaralas en "
        f"SIN_CLASIFICAR_A_PROPOSITO con su motivo → {faltan}")


def test_las_exclusiones_declaradas_siguen_siendo_ciertas(clases,
                                                          gasto_del_catalogo):
    """En los dos sentidos: una exclusión que ya se clasificó tiene que salir de
    la lista, y una que ya no existe en el catálogo también. Si no, la lista se
    llena de perdones viejos y deja de decir nada."""
    con_regla = {(c["dept_code"], c["account"]) for c in clases if c["account"]}
    del_catalogo = set(gasto_del_catalogo)

    ya_clasificadas = sorted(SIN_CLASIFICAR_A_PROPOSITO.keys() & con_regla)
    assert not ya_clasificadas, (
        "estas cuentas están declaradas como «sin clasificar a propósito» y "
        f"la semilla SÍ las clasifica: sacalas de la lista → {ya_clasificadas}")

    fantasmas = sorted(SIN_CLASIFICAR_A_PROPOSITO.keys() - del_catalogo)
    assert not fantasmas, (
        "estas cuentas ya no están en `orden_plantilla.json`: la exclusión "
        f"sobra → {fantasmas}")

    for par, motivo in SIN_CLASIFICAR_A_PROPOSITO.items():
        assert motivo.strip(), f"la exclusión {par} no dice por qué"


def test_los_departamentos_que_no_se_operan_no_estan_activos(deptos):
    """Owner, 2026-09-03: Ojochal opera **Rooms, Spa y Tours**, más Transporte;
    el Club Madresal es de Amarena y salió el mismo día.

    Se comprueba lo que se sabe de la propiedad, no la lista entera: el resto de
    los departamentos del grupo siguen en el catálogo —para que un movimiento
    suyo tenga departamento y no caiga por descarte— pero **no activos**.
    """
    if HOTEL_ID != "OJO":
        pytest.skip("la lista de departamentos operados es de Ojochal Gardens")
    estado = {d["slug"]: d["status"] for d in deptos}
    no_se_operan = ["fb", "private-bar", "gift-shop", "tienda", "innoceana",
                    "crowther-lab", "claro-huerta", "cafeteria",
                    "club-madresal", "area-recreativa", "miscelaneos"]
    activos_de_mas = [s for s in no_se_operan
                      if estado.get(s) == DEPT_ACTIVO]
    assert not activos_de_mas, (
        "departamentos que Ojochal no opera, marcados como activos → "
        f"{activos_de_mas}")
    for s in ("rooms", "spa", "tours", "transportation"):
        assert estado.get(s) == DEPT_ACTIVO, f"{s} tendría que estar activo"


def test_la_clasificacion_es_internamente_coherente(deptos, clases):
    """Tres invariantes baratas que ya costaron un bug en CWL."""
    slugs = {d["slug"] for d in deptos}
    for c in clases:
        assert c["property_code"] == HOTEL_ID, (
            f"fila de otra propiedad en la semilla de {HOTEL_ID}: {c}")
        assert c["be_department_slug"] in slugs, (
            f"departamento inexistente: {c['be_department_slug']}")
        # `pct_variable` es el ÚNICO porcentaje que se guarda; el fijo se
        # deriva. Que la etiqueta y el número digan lo mismo.
        esperado = "1.0" if c["original_class"] == "Variable" else "0.0"
        assert c["pct_variable"] == esperado, (
            f"{c['dept_code']}/{c['account']}: {c['original_class']} con "
            f"pct_variable={c['pct_variable']}")
        # Las filas LINEA van sin cuenta; las de cuenta, con cuenta.
        assert (c["map_source"] == "LINEA") == (not c["account"]), (
            f"map_source y cuenta no concuerdan: {c}")

    # §2.6: EXACTAMENTE una fila LINEA por `pl_line`. Si dos compiten, gana la
    # primera del archivo y la resolución deja de ser reproducible.
    lineas = [c["pl_line"] for c in clases if c["map_source"] == "LINEA"]
    assert len(lineas) == len(set(lineas)), "dos filas LINEA para la misma línea"
