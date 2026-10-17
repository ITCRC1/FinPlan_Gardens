# -*- coding: utf-8 -*-
"""El consolidado manda dos cifras de Rooms. La que no es, lo dice.

## Lo que se midió

`/consolidado/rooms/escenario/{id}/` arma su respuesta con varios bloques. Dos
de ellos traen Rooms, y se calculan por caminos distintos:

    monthly        ← `load_revenue_results`, el mismo del P&L
    by_room_type   ← rack × ocupación por tipo, SIEMPRE

El 2026-10-16, con `BUDGET Working 2027` recién conectado al modelo por
segmento:

    monthly        $402.091,65   2.263 noches
    by_room_type   $273.207,99   2.663 noches

$128.883 de diferencia dentro de **una misma respuesta**, sin error y sin que
ningún total deje de cuadrar consigo mismo. Cuál de las dos lee Hotel
Consolidation decide si muestra el presupuesto del owner o el modelo viejo.

## Por qué no se borra ni se reparte

El modelo por segmento no tiene dimensión de tipo de habitación: reparte por
canal de venta. Repartir ese ingreso entre las villas para que los totales
cuadren sería **dar por medido algo que nadie midió**. Se declara y listo.
"""
import inspect

from app.api import revenue_api


FUENTE = inspect.getsource(revenue_api.get_revenue_by_room_type)


def test_declara_de_que_modelo_salio():
    """Sin esto, las dos cifras se ven igual de autorizadas."""
    assert '"rooms_source": fuente_rooms' in FUENTE
    assert '"es_la_fuente_de_rooms": es_la_fuente' in FUENTE


def test_la_bandera_se_apaga_cuando_rooms_sale_de_los_canales():
    assert 'es_la_fuente = fuente_rooms != "canales"' in FUENTE


def test_cuando_no_es_la_fuente_dice_donde_esta_la_buena():
    """Una bandera en `false` deja al consumidor sin saber qué leer."""
    assert '"nota"' in FUENTE
    assert "monthly.rooms" in FUENTE


def test_no_inventa_un_reparto_por_tipo_de_habitacion():
    """Si alguien hace que las filas sumen el total del modelo por segmento,
    el cuadro pasa a decir qué villa vendió qué — y eso no lo sabe nadie."""
    for inventado in ("prorrate", "proporcional_por_villa", "escalar_filas"):
        assert inventado not in FUENTE


def test_las_filas_se_siguen_devolviendo():
    """Declarar no es borrar: el cuadro sigue describiendo el modelo por
    tarifa, que es información real sobre los supuestos del escenario."""
    assert '"months": months' in FUENTE
    assert '"annual": _aggregate_room_type(' in FUENTE
