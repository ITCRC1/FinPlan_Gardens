# -*- coding: utf-8 -*-
"""El Tablero del Presupuesto: qué filas existen, y quién decide eso.

Owner, 2026-11-03: *«quiero que asignes todas las tareas a Bismark»* · *«que
tenga opción de escoger pendiente, en proceso y finalizado y bloquear y que se
pueda guardar»* · *«revisá la naturaleza de cada sección y las que no apliquen
que tengan la opción que se esconda»* · *«planilla es extensa, opex es
extensa»*.

## Qué estaba mal

La pantalla armaba la lista de filas sola, con una COPIA del catálogo de
departamentos escrita en el navegador (`CWL_DEPTS`). De ahí salían dos
problemas, y los dos los paga el usuario:

1. Las seis secciones mostraban los mismos 37 departamentos. Pedía aprobar
   «Ingreso de Mantenimiento» y «Costo de venta de Administración», que no
   existen — 126 casillas de las cuales buena parte no son nada.
2. No se enteraba de lo que la propiedad había apagado en provisionamiento, así
   que un departamento escondido en su checkbook seguía pidiendo aprobación
   acá.

## La regla que se cuida

La estructura la arma el backend desde donde YA vive la verdad: el catálogo de
departamentos (`is_revenue_dept`), el interruptor de provisionamiento
(`depts_habilitados`) y los conteos de datos (`_conteos`). Si alguien vuelve a
escribir la lista en la pantalla, vuelven los dos problemas de arriba — y nada
falla, sólo aparecen filas de más.
"""
import pathlib

import pytest

from app.api.collab_api import NONOP_REFS, SECCION_CLASE, SECCION_DIM
from app.models.section_assignment import SECTIONS

RAIZ = pathlib.Path(__file__).resolve().parents[1]
PANTALLA = RAIZ.parent / "frontend" / "app" / "board" / "page.tsx"


# ── La naturaleza de cada sección ────────────────────────────────────────────

def test_cada_seccion_de_departamentos_declara_su_dimension():
    """`master` es una fila sola y `nonop` son rubros below-GOP: no tienen
    departamento. Las otras cuatro sí, y cada una tiene que decir con qué
    dimensión de provisionamiento se filtra."""
    assert set(SECCION_DIM) | {"master", "nonop"} == set(SECTIONS)


def test_las_dimensiones_existen_en_provisionamiento():
    """Si una sección nombrara una dimensión que el provisionamiento no tiene,
    su filtro no haría nada y la sección volvería a mostrarlo todo."""
    from app.api.provisioning_api import DIMS_DEPT
    assert set(SECCION_DIM.values()) <= set(DIMS_DEPT)


def test_cada_seccion_declara_la_clase_de_cuenta_que_la_define():
    """Un departamento aparece en una sección si tiene reglas de mapeo de esa
    clase. Es lo que baja Costos de venta de 38 departamentos a 17 — fuera
    Administración, Ventas y Mantenimiento, dentro Information System, que sí
    tiene costo de venta en las cuentas 5400-5404."""
    assert SECCION_CLASE == {"revenue": "4", "costs": "5",
                             "payroll": "6", "opex": "7"}
    assert set(SECCION_CLASE) == set(SECCION_DIM)


def test_los_tres_filtros_siguen_puestos():
    """Los tres salen de verdad que ya estaba escrita en otro lado. Si uno se
    cae, el tablero vuelve a pedir aprobar casillas que no existen — y no falla
    nada, sólo aparecen filas de más."""
    import inspect
    from app.api import collab_api
    fuente = inspect.getsource(collab_api.tablero_del_escenario)
    assert "_depts_por_clase" in fuente, "volvió a ofrecer todas las secciones"
    assert "is_revenue_dept" in fuente, (
        "las reglas 4xxx solas dejan entrar a Administración y Mantenimiento, "
        "que tienen ingreso misceláneo pero no le venden a nadie")
    assert "depts_habilitados" in fuente, (
        "el tablero dejó de respetar lo que la propiedad apagó")
    assert "_conteos" in fuente, (
        "sin los conteos, esconder un departamento es a ciegas")


def test_el_ingreso_no_miente_diciendo_sin_datos():
    """`_conteos` sólo cubre planilla, OPEX y costos. Si Ingreso emitiera
    `datos: 0`, sus 14 departamentos dirían «sin datos» y ese cero invitaría a
    esconder justo lo que factura."""
    import inspect
    from app.api import collab_api
    fuente = inspect.getsource(collab_api.tablero_del_escenario)
    assert 'CON_CONTEO = {"PAYROLL", "OPEX", "COST"}' in fuente
    assert "if dim in CON_CONTEO:" in fuente


def test_los_rubros_de_abajo_del_gop_no_son_departamentos():
    """Mgmt fee, seguros, capital, financieros y depreciación no tienen depto:
    si salieran del catálogo, el filtro por dimensión los borraría."""
    assert NONOP_REFS and all(not r.isdigit() for r in NONOP_REFS)


# ── La pantalla no vuelve a armar la lista sola ──────────────────────────────

@pytest.mark.skipif(not PANTALLA.exists(), reason="no está el frontend")
def test_la_pantalla_usa_la_estructura_del_backend():
    texto = PANTALLA.read_text(encoding="utf-8")
    assert "r.tablero" in texto, (
        "la pantalla volvió a armar las filas sola: vuelven «Ingreso de "
        "Mantenimiento» y los departamentos apagados")
    assert "GRUPOS" in texto


@pytest.mark.skipif(not PANTALLA.exists(), reason="no está el frontend")
def test_esconder_llama_al_provisionamiento_y_no_a_un_interruptor_propio():
    """Esconder acá y esconder en el checkbook tienen que ser EL MISMO acto.
    Un interruptor propio del tablero dejaría dos verdades y la primera vez que
    discrepen nadie sabría cuál manda."""
    texto = PANTALLA.read_text(encoding="utf-8")
    assert "saveProvisioningDepts" in texto
    assert "it.madre" in texto, (
        "el provisionamiento rechaza un hijo suelto: hay que mandarle la madre")


@pytest.mark.skipif(not PANTALLA.exists(), reason="no está el frontend")
def test_el_selector_ofrece_los_tres_estados_que_pidio_el_owner():
    texto = PANTALLA.read_text(encoding="utf-8")
    assert 'const ESTADOS = ["pending", "in_progress", "approved"]' in texto
    assert "!ESTADOS.includes(status)" in texto, (
        "una fila en revisión tiene que poder mostrar su estado real: sin esa "
        "opción el selector la pintaría como otra cosa")


@pytest.mark.skipif(not PANTALLA.exists(), reason="no está el frontend")
def test_asignar_todo_es_un_solo_viaje():
    """126 casillas una por una son 126 llamadas y 126 recargas."""
    texto = PANTALLA.read_text(encoding="utf-8")
    assert "asignarTableroEnBloque" in texto
