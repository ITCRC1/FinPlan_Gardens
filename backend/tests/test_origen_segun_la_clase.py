# -*- coding: utf-8 -*-
"""El mapeo dice lo mismo que la clase de la cuenta.

Owner, 2026-11-10 (en CWL, portado a Ojochal): «asegurate que 4 son ingresos,
5 costos, 6 planilla, 7 opex y 8 gastos de la propiedad y 9 stats».

El cálculo separa por el primer dígito (`pl_engine`); estas pruebas exigen que
el mapeo tampoco lo contradiga: ni la sección donde cae, ni el rótulo de origen
(migración 150).
"""
import importlib.util
import json
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent
MAPEO = json.loads((RAIZ / "app" / "seed_data" / "mapping_pl.json").read_text(encoding="utf-8"))

#: Secciones posibles por clase. La 4 en una sección de gasto es el crédito de
#: «Distribución» (4900/4901/4999) del reparto; la 5 de overhead es el costo de
#: cafetería y TI.
SECCIONES = {
    "4": {"REVENUES", "OPERATING EXPENSES", "OVERHEAD EXPENSES"},
    "5": {"COST OF SALES", "OVERHEAD COST OF SALES"},
    "6": {"OPERATING EXPENSES", "OVERHEAD EXPENSES"},
    "7": {"OPERATING EXPENSES", "OVERHEAD EXPENSES"},
    "8": {"CAPITAL", "DEPRECIATION", "FINANCIAL EXPENSES", "OWNER / NON-OP EXPENSES",
          "TAX / NET PROFIT"},
}
ORIGEN = {"6": {"Payroll", "PAYROLL"}, "7": {"Opex", "OpEx", "Operating Expense"}}


def test_cada_fila_cae_en_una_seccion_de_su_clase():
    malas = [(x["source_department"], x["account_code"], x["report_section"])
             for x in MAPEO["account_mapping"]
             if x["report_section"] not in SECCIONES[str(x["account_code"])[0]]]
    assert not malas, malas[:10]


def test_la_4_en_una_seccion_de_gasto_es_solo_el_reparto():
    malas = [(x["source_department"], x["account_code"])
             for x in MAPEO["account_mapping"]
             if str(x["account_code"]).startswith("4") and x["report_section"] != "REVENUES"
             and not str(x["account_code"]).startswith("49")]
    assert not malas, malas[:10]


def test_ninguna_estadistica_esta_en_el_pl():
    assert not [x for x in MAPEO["account_mapping"] if str(x["account_code"]).startswith("9")]


def test_el_origen_de_planilla_y_opex_dice_su_clase():
    malas = [(x["source_department"], x["account_code"], x["source_origin"])
             for x in MAPEO["account_mapping"]
             if str(x["account_code"])[0] in ORIGEN
             and x["source_origin"] not in ORIGEN[str(x["account_code"])[0]]]
    assert not malas, malas[:10]


def test_la_migracion_150_renombra_a_lo_que_dice_el_archivo():
    """Cada fila que la migración renombra tiene que existir en el archivo con el
    rótulo nuevo; si no, la semilla insertaría otra y quedarían dos."""
    ruta = RAIZ / "alembic" / "versions" / "150_origen_del_mapeo_segun_la_clase.py"
    spec = importlib.util.spec_from_file_location("m150", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    en_archivo = {(x["report_id"], x["source_department"], str(x["account_code"]), x["source_origin"])
                  for x in MAPEO["account_mapping"] if not x.get("vigente_desde")}
    assert len(mod.CAMBIOS) == 103
    for rep, dep, cta, viejo, nuevo in mod.CAMBIOS:
        assert (rep, dep, cta, nuevo) in en_archivo, (dep, cta, nuevo)
        assert (rep, dep, cta, viejo) not in en_archivo, (dep, cta, viejo)
