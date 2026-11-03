# -*- coding: utf-8 -*-
"""El resumen de costos de TODOS los departamentos, abajo del checkbook.

Owner, 2026-11-03, sobre la pantalla de Cost of Sales: *«puedes darme abajo el
resumen del costo, arriba el que estoy cambiando y abajo resumen de todos los
costos»*. Editando un departamento no se veía en qué quedaba el conjunto.

Lo que se cuida acá es que el resumen **no contradiga al P&L**, que es lo único
que lo haría inútil. Dos formas de lograrlo, y las dos tienen prueba:

1. Contar a alguien dos veces. El checkbook trabaja al nivel del padre (0120
   A&B) y el reparto cae en los hijos (0122 Cocina, 0123 Restaurante);
   `lineas_del_allocation` ya recoge a los hijos cuando se le pide el padre.
2. Dejar fuera lo repartido. El P&L suma las DOS corrientes —lo digitado y lo
   que cae por allocation—; un resumen que sólo muestre la primera descuadra
   contra el P&L por el monto del reparto.
"""
from app.api.costs_api import depts_del_resumen


def test_un_hijo_no_se_lista_si_su_padre_esta():
    """`lineas_del_allocation(0120)` ya trae a Cocina y Restaurante. Listarlos
    aparte sumaría su reparto dos veces."""
    padres = {"0122": "0120", "0123": "0120"}
    assert depts_del_resumen({"0120", "0122", "0123"}, padres) == ["0120"]


def test_un_hijo_huerfano_si_se_lista():
    """Si el padre no está, nadie lo recoge: esconderlo es peor que duplicarlo.
    Es el caso del 0162, que carga costo de venta y no tiene checkbook."""
    padres = {"0162": "0160"}
    assert depts_del_resumen({"0162", "0152"}, padres) == ["0152", "0162"]


def test_un_departamento_sin_padre_siempre_entra():
    assert depts_del_resumen({"0152"}, {}) == ["0152"]


def test_no_se_pierde_nadie_ni_se_repite():
    """La lista es un subconjunto de los candidatos, sin repetidos y ordenada —
    es lo que hace que el total de abajo se pueda leer de un vistazo."""
    padres = {"0122": "0120", "0123": "0120", "0141": "0140"}
    cands = {"0120", "0122", "0123", "0140", "0141", "0152", "0220"}
    salida = depts_del_resumen(cands, padres)
    assert salida == sorted(set(salida))
    assert set(salida) <= cands
    assert set(salida) == {"0120", "0140", "0152", "0220"}


def test_el_resumen_devuelve_las_dos_corrientes_separadas():
    """`propio` y `repartido` van aparte a propósito: son cosas distintas —una
    se edita y la otra no— y el P&L suma las dos. Si el endpoint dejara de
    emitirlas por separado, la pantalla no podría explicar de dónde sale el
    número."""
    import inspect
    from app.api import costs_api
    fuente = inspect.getsource(costs_api.costs_summary)
    for campo in ('"propio"', '"repartido"', '"total"', '"anual"', '"reparte"'):
        assert campo in fuente, f"el resumen dejó de emitir {campo}"
    assert "lineas_del_allocation" in fuente, (
        "el resumen dejó de usar la misma función que el checkbook: una "
        "segunda suma del reparto es una segunda verdad que mantener a mano")
