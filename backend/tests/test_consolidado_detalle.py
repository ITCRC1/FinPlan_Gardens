# -*- coding: utf-8 -*-
"""Posiciones, planilla y OPEX para el Excel en vivo (owner, 2026-11-11).

«mete un P&L usali, posiciones y checkbook de gastos y planilla». Lo que estas
pruebas cuidan:

* va en un módulo APARTE: `consolidado_api` sigue siendo el contrato entre
  propiedades, sin detalle (`test_el_consolidado_no_expone_detalle`);
* misma puerta (llave de solo lectura o sesión) y sin `_guard` encima, que la
  dejaría muerta;
* el nombre de la persona NO viaja;
* posiciones y planilla salen del MISMO armado que el reporte de la pantalla;
* el libro: cada hoja nueva tiene su consulta, y todas comparten el preámbulo.
"""
import io
import pathlib
import re

BACK = pathlib.Path(__file__).resolve().parents[1]
FUENTE = (BACK / "app" / "api" / "consolidado_detalle_api.py").read_text(encoding="utf-8")
LIBRO = BACK / "scripts" / "gl_en_vivo"


def _codigo(src: str) -> str:
    """El fuente sin comentarios ni docstrings: lo que de verdad corre."""
    sin_doc = re.sub(r'"""[\s\S]*?"""', "", src)
    return "\n".join(l.split("#", 1)[0] for l in sin_doc.splitlines())


def test_va_aparte_del_contrato_entre_propiedades():
    contrato = (BACK / "app" / "api" / "consolidado_api.py").read_text(encoding="utf-8")
    for prohibido in ("PayrollConceptEntry", "OpexEntry", "planilla_por_posicion"):
        assert prohibido not in contrato


def test_va_con_la_llave_de_solo_lectura_y_sin_guard():
    assert FUENTE.count("Depends(lector_del_consolidado)") == 2
    main = io.open(BACK / "app" / "main.py", encoding="utf-8").read()
    linea = [l for l in main.splitlines()
             if "consolidado_detalle_router" in l and "include_router" in l]
    assert linea and "_guard" not in linea[0]


def test_el_nombre_de_la_persona_no_viaja():
    assert "employee_name" not in _codigo(FUENTE)


def test_posiciones_reusa_el_reporte_de_la_pantalla():
    assert "planilla_por_posicion(" in FUENTE


def test_escoge_el_escenario_como_el_resto_del_consolidado():
    assert "_escoger_escenario(" in FUENTE
    assert 'raise ErrorApi(404, "consolidado.sin_escenario' in FUENTE


def test_el_libro_y_las_consultas_dicen_las_mismas_hojas():
    ps1 = (LIBRO / "add_queries.ps1").read_text(encoding="utf-8")
    build = (LIBRO / "build_gl_live.py").read_text(encoding="utf-8")
    hojas = re.search(r"HOJAS_EXTRA = \((.*?)\)", build).group(1)
    for hoja in re.findall(r'"([^"]+)"', hojas):
        assert f'"{hoja}"' in ps1, f"la hoja {hoja} no tiene consulta"
    for archivo in ("pl.m", "posiciones.m", "planilla.m", "opex.m"):
        m = (LIBRO / archivo).read_text(encoding="utf-8")
        assert "//#COMUN#" in m, archivo
        assert f'"{archivo}"' in ps1, archivo


def test_el_aviso_de_una_version_que_falla_cae_en_una_columna_de_texto():
    """`FalloEn` escribe el aviso en la TERCERA columna. Si esa columna se tipa
    como número, el aviso se pierde y la versión baja vacía sin decir por qué
    (pasó con «Orden» en la hoja P&L)."""
    for archivo in ("pl.m", "posiciones.m", "planilla.m", "opex.m"):
        m = (LIBRO / archivo).read_text(encoding="utf-8")
        tercera = re.search(r'Cols = \{"[^"]+","[^"]+","([^"]+)"', m).group(1)
        numericas = re.search(r"Apilar\(Cols, Traer,([\s\S]*?)\)\s*\nin", m).group(1)
        assert f'"{tercera}"' not in numericas, (archivo, tercera)
