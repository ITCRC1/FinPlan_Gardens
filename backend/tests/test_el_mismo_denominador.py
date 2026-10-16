# -*- coding: utf-8 -*-
"""Los dos modos de ingreso dividen por las MISMAS noches disponibles.

## El defecto que esto persigue

El modo `checkbook` leía las noches disponibles de `ScenarioStat`, y
`sincronizar_noches` escribe `ScenarioStat` desde el resultado. Círculo cerrado:
el número se confirmaba a sí mismo y el inventario de la propiedad no entraba
nunca.

Medido el 2026-10-16 en Ojochal: el owner había corregido el inventario a 11
unidades de venta y los cinco escenarios en modo `checkbook` seguían con 16 por
día —5.840 noches al año contra 4.015—. **Recalcular no lo arreglaba**: lo
volvía a escribir igual.

La plata no se movía, así que nada fallaba. Lo que salía mal era todo lo que se
divide por noches: ocupación, RevPAR, TRevPAR y el punto de equilibrio. Y para
el lado peligroso: con el denominador inflado la ocupación se ve **más baja** de
lo que es, y el equilibrio **más fácil** de alcanzar.
"""
import inspect

from app.engine import recalculate


CHECKBOOK = inspect.getsource(recalculate.revenue_results_from_checkbook)
DRIVERS = inspect.getsource(recalculate.load_revenue_results)


def test_el_checkbook_NO_lee_las_disponibles_de_las_estadisticas():
    """La línea que cerraba el círculo. Si vuelve, vuelve el defecto."""
    assert "r.rooms_available = int(st.rooms_available" not in CHECKBOOK, (
        "`revenue_results_from_checkbook` volvió a leer las noches disponibles "
        "de `ScenarioStat`, que es la misma tabla que el recálculo escribe "
        "desde este resultado: el número se confirma a sí mismo y el "
        "inventario de la propiedad no entra nunca")


def test_el_checkbook_las_calcula_de_unidades_por_dias():
    assert "unidades * CALENDAR_DAYS[month - 1]" in CHECKBOOK


def test_un_ACTUAL_conserva_lo_que_midio():
    """En un presupuesto las disponibles son un supuesto; en un ACTUAL son un
    hecho.

    En Ojochal 2025 van de 7,2 a 11,9 unidades por dia porque las villas fueron
    abriendo. Aplanarlas al inventario de hoy contaria como disponible una villa
    que todavia no existia, y la ocupacion de un año cerrado bajaria —de 30,8 %
    a 28,0 %— sin que se hubiera movido una noche vendida.
    """
    assert "es_actual" in CHECKBOOK
    assert 'ACTUAL' in CHECKBOOK
    assert "medidas if (es_actual and medidas)" in CHECKBOOK


def test_un_ACTUAL_sin_medicion_cae_al_inventario():
    """Sin estadistica, o con la estadistica en cero, no hay nada que
    preservar: usar ese cero seria dividir por cero en la ocupacion."""
    assert "es_actual and medidas" in CHECKBOOK


def test_las_ocupadas_y_los_pax_SI_salen_de_las_estadisticas():
    """Sólo el denominador se calcula. Las noches vendidas son un dato real y
    no se pueden derivar del inventario."""
    assert "r.rooms_occupied = st.rooms_occupied" in CHECKBOOK
    assert "r.guests = st.guests" in CHECKBOOK


def test_los_dos_caminos_resuelven_las_unidades_igual():
    """Mismo origen y mismas dos fuentes, en el mismo orden.

    No se compara el código letra por letra —uno necesita el detalle por tipo y
    el otro sólo el total—, sino que los dos miren `RoomTypeConfig` y después
    el override de `ScenarioMaster`. Que uno filtre por `active` y el otro no,
    o que uno se olvide del override, da dos ocupaciones para el mismo mes.
    """
    unidades = inspect.getsource(recalculate._unidades_del_escenario)
    for fuente, nombre in ((unidades, "_unidades_del_escenario"),
                           (DRIVERS, "load_revenue_results")):
        assert "RoomTypeConfig" in fuente, nombre
        assert "ScenarioMaster" in fuente, nombre
        assert "units_json" in fuente, nombre
        # Ninguno de los dos filtra por `active`: una categoría desactivada con
        # unidades sigue siendo inventario, y excluirla en UN camino solamente
        # es la forma más silenciosa de que difieran.
        assert "RoomTypeConfig.active" not in fuente, (
            f"{nombre} filtra por `active` y el otro camino no: los dos modos "
            f"darían ocupaciones distintas para el mismo mes")


def test_el_checkbook_usa_el_mismo_calendario_que_el_motor():
    """`CALENDAR_DAYS`, no `calendar.monthrange`.

    No es lo mismo en años bisiestos, y la gracia de esto es que los dos
    caminos den IDÉNTICO. El día que el motor pase a contar bisiestos, los dos
    pasan juntos — por eso comparten la constante en vez de tener cada uno su
    forma de contar los días.
    """
    assert "CALENDAR_DAYS" in CHECKBOOK
    assert "monthrange" not in CHECKBOOK


def test_el_helper_de_unidades_es_uno_solo():
    """Vive en el motor y se llama desde la rama de checkbook."""
    assert "_unidades_del_escenario(session, scenario)" in CHECKBOOK
