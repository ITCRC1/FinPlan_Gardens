# -*- coding: utf-8 -*-
"""Ninguna pantalla calcula los KPIs de Rooms por su cuenta.

## Lo que se vio

Owner, 2026-10-16, señalando el bloque de KPIs del Revenue Checkbook con el
ingreso de Rooms ya corregido debajo:

    la pantalla   1.831 noches · 45,6 % · ADR $102,59
    el motor      2.263 noches · 56,4 % · ADR $177,68

El mismo cuadro mostraba el ingreso nuevo y la ocupación vieja. Nada fallaba.

La causa: `revenue/checkbook` calculaba esos KPIs **en el navegador** —
ocupación × unidades × días para las noches, y rack × net factor para el
ingreso—, o sea el modelo de TARIFAS, mirara lo que mirara `rooms_source`. Un
tercer motor, con el agregado de que el texto de la propia pantalla decía que
los KPIs venían de las estadísticas del escenario.

Es la misma lección que ya dejaron `get_monthly_revenue` (que tenía su propio
motor y mostraba Ojochal en cero) y `_ingreso_de_driver` (que escribía en una
sola de las dos fuentes). Por eso la guarda es estructural y no una prueba de
números: lo que hay que impedir es que **vuelva a existir** la cuenta paralela.
"""
import re

from tests._rutas import FRONT

PAGINA = FRONT / "app" / "revenue" / "checkbook" / "page.tsx"
FUENTE = PAGINA.read_text(encoding="utf-8")


def test_los_kpis_vienen_de_la_puerta_del_motor():
    """`revenue/monthly/` es la misma que lee el P&L y el consolidado."""
    assert "getMonthlyRevenue(sid)" in FUENTE


def test_la_pantalla_NO_recalcula_las_noches_ocupadas():
    """`ocupación × unidades × días` acá es el modelo de tarifas escrito a
    mano: ignora `rooms_source` y no se entera de ningún otro modelo."""
    bloque = FUENTE[FUENTE.index("const load ="):FUENTE.index("setDirty(false)")]
    assert "getOccupancyPct" not in bloque
    assert "daysInMonth(year" not in bloque


def test_la_pantalla_NO_recalcula_el_ingreso_de_rooms():
    """`nights * rack * netFactor` es la otra mitad del mismo motor."""
    bloque = FUENTE[FUENTE.index("const load ="):FUENTE.index("setDirty(false)")]
    assert "getRackRates" not in bloque
    assert re.search(r"nights\s*\*\s*rk", bloque) is None


def test_los_pax_salen_del_mes_y_no_del_supuesto():
    """`pax_per_night` del tipo de habitación es el SUPUESTO. Si el modelo por
    segmento movió las noches, el supuesto deja de describir al mes — y el
    cuadro mostraría huéspedes de un mes que no pasó."""
    assert "paxTot" in FUENTE and "occTot" in FUENTE


def test_el_texto_de_la_pantalla_no_miente():
    """Decía «los KPIs de Rooms vienen de Estadísticas del escenario» mientras
    los calculaba sola. Ahora salen del motor, que es el que escribe esas
    estadísticas — así que el texto por fin es cierto."""
    assert "getMonthlyRevenue" in FUENTE
