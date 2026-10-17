# -*- coding: utf-8 -*-
"""Con el modelo por segmento conectado, ROOMS baja al checkbook.

## Lo que se vio

Owner, 2026-10-16: *«no está conectando con revenue checkbook 2027 budget»*.

Y la pantalla le daba la razón. El escenario estaba conectado y medido por
todos lados daba bien:

    P&L / consolidado   $402.091,65
    checkbook (ROOMS)   $273.207,98   ← el monto tipeado ANTES de conectar

Ninguno de los dos fallaba. Cada uno cuadraba consigo mismo. El owner abrió el
checkbook, vio el número viejo, y la conclusión razonable fue «no se conectó».

## Por qué la guarda existía, y por qué la excepción es de UNA línea

`sincronizar_ingreso_al_checkbook` no escribe en modo `checkbook` porque ahí
las filas son montos **tipeados** y son la fuente del P&L: pisarlas con el
derivado le borra el presupuesto a alguien.

Eso sigue siendo cierto para Spa, Tours y todo lo demás. Lo que cambió es que
**ROOMS deja de ser tipeada** en cuanto se conecta el modelo por segmento: la
calcula el tarifario. Dejarla congelada es exactamente el desfase que esta
función existe para impedir.
"""
import inspect

from app.engine import recalculate

FUENTE = inspect.getsource(recalculate.sincronizar_ingreso_al_checkbook)


def test_en_checkbook_SIN_el_modelo_sigue_sin_escribir():
    """La guarda vieja no se aflojó: un escenario de checkbook normal conserva
    sus montos tipeados."""
    assert 'if getattr(scenario, "rooms_source", "tarifas") != "canales":' in FUENTE
    assert "return 0" in FUENTE


def test_con_el_modelo_conectado_baja_SOLO_rooms():
    """⚠️ Por LÍNEA, no por escenario. Si bajaran todas, el Spa y los Tours que
    el usuario digitó se irían a cero —el modelo por segmento no los calcula— y
    el P&L seguiría cuadrando contra el número equivocado."""
    assert "solo_rooms = True" in FUENTE
    assert 'derivado = {k: v for k, v in derivado.items() if k == "ROOMS"}' in FUENTE


def test_la_condicion_es_rooms_source_y_no_el_hotel_ni_el_anio():
    """Misma regla que el resto del modelo: lo decide el interruptor del
    escenario, no una lista de propiedades que alguien tenga que mantener."""
    bloque = FUENTE[FUENTE.index("solo_rooms = False"):
                    FUENTE.index("derivado: dict[str, list[Decimal]] = {}")]
    assert "rooms_source" in bloque
    for prohibido in ("hotel_id", "scenario.year", "HOTEL_ID"):
        assert prohibido not in bloque, prohibido


def test_los_meses_cerrados_se_siguen_respetando():
    """Un mes cerrado no se reescribe, venga de donde venga el número."""
    assert "if cerrados and (i + 1) in cerrados:" in FUENTE


def test_el_recalculo_lo_llama():
    """Si no se llama desde el recálculo, el checkbook vuelve a ser una foto de
    la última vez que alguien apretó un botón a mano."""
    fuente = inspect.getsource(recalculate.recalculate_scenario)
    assert "sincronizar_ingreso_al_checkbook(" in fuente
