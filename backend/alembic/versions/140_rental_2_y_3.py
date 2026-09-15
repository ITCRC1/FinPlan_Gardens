"""0155 y 0156 pasan a ser Rental #2 y Rental #3.

Revision ID: 140
Revises: 139
Create Date: 2026-09-15

Eran Innoceana (0155) y Crowther Lab (0156), heredados del clon de Corcovado.
Ojochal Gardens no opera ninguno de los dos —están apagados en Provisionamiento
desde el 2026-09-08— y pasan a ser departamentos de alquiler.

QUE SE RENOMBRA Y QUE NO
========================
Se renombra el VOCABULARIO DEL REPORTE:

    REV_/OPEX_/COS_/PROFIT_INNOCEANA     -> ..._RENTAL_2
    REV_/OPEX_/COS_/PROFIT_CROWTHER_LAB  -> ..._RENTAL_3

NO se toca `revenue_entries.line = 'INNOCEANA'`, que es la linea de ingreso del
checkbook. Ese es un VALOR GUARDADO EN FILAS, no un rotulo: renombrarlo obliga a
migrar datos sin que nadie vea la diferencia, porque lo que se muestra en
pantalla es `REVENUE_LINE_LABELS`, que si cambia a «Rental #2».

POR QUE HACE FALTA LA MIGRACION (la misma trampa de la 139)
===========================================================
1. `report_line_config` se busca por (report_id, line_code). Al renombrar, el
   seed inserta las nuevas y DEJA las viejas: no borra por ausencia, a
   proposito. Sin esto quedarian las dos versiones activas y el reporte
   dibujaria el departamento dos veces.

2. `source_department` SI forma parte de `uq_account_mapping`. El JSON ya trae
   «Departamento de Rental #2»; si la base se quedara con el nombre viejo, el
   seed leeria las 72 reglas como nuevas y las insertaria al lado de las
   viejas — cada monto contado DOS VECES, sin error y sin aviso. Por eso el
   UPDATE va aca y no se confia al seed. El orden lo garantiza el Procfile:
   `alembic upgrade head` corre antes que `python -m app.seed`.

⚠️ NO se cambia `enabled` en `dept_enablement`: el owner pidio dejarlos apagados
   por ahora (2026-09-15). Solo se actualiza la nota, para que diga por que.
"""
from alembic import op
import sqlalchemy as sa

revision = "140"
down_revision = "139"
branch_labels = None
depends_on = None

LINEAS = {
    "REV_INNOCEANA": ("REV_RENTAL_2", "Rental #2"),
    "OPEX_INNOCEANA": ("OPEX_RENTAL_2", "Rental #2"),
    "COS_INNOCEANA": ("COS_RENTAL_2", "Rental #2 Cost"),
    "PROFIT_INNOCEANA": ("PROFIT_RENTAL_2", "Rental #2"),
    "REV_CROWTHER_LAB": ("REV_RENTAL_3", "Rental #3"),
    "OPEX_CROWTHER_LAB": ("OPEX_RENTAL_3", "Rental #3"),
    "COS_CROWTHER_LAB": ("COS_RENTAL_3", "Rental #3 Cost"),
    "PROFIT_CROWTHER_LAB": ("PROFIT_RENTAL_3", "Rental #3"),
}
CALCULOS = {
    "PROFIT_RENTAL_2": "REV_RENTAL_2 - OPEX_RENTAL_2 - COS_RENTAL_2",
    "PROFIT_RENTAL_3": "REV_RENTAL_3 - OPEX_RENTAL_3 - COS_RENTAL_3",
}
DEPTOS = {
    "Departamento de INNOCEANA": "Departamento de Rental #2",
    "Departamento de INNOCEANA (costo de snacks)":
        "Departamento de Rental #2 (costo de snacks)",
    "Departamento CROWTHER LAB": "Departamento Rental #3",
}
NOMBRES_DEPTO = {"0155": "Rental #2", "0156": "Rental #3"}


def upgrade() -> None:
    c = op.get_bind()

    # 1. Si ya existiera la nueva (renombre a medias), la vieja sobra. Se borra
    #    PRIMERO: renombrar con la nueva presente choca contra uq_report_line_code.
    for viejo, (nuevo, _n) in LINEAS.items():
        c.execute(sa.text("""
            DELETE FROM report_line_config
             WHERE report_id = 'P&L_DETAIL_OWNERS' AND line_code = :viejo
               AND EXISTS (SELECT 1 FROM report_line_config n
                            WHERE n.report_id = 'P&L_DETAIL_OWNERS'
                              AND n.line_code = :nuevo)
        """), {"viejo": viejo, "nuevo": nuevo})

    # 2. report_line_config: codigo y rotulo.
    for viejo, (nuevo, nombre) in LINEAS.items():
        c.execute(sa.text("""
            UPDATE report_line_config SET line_code = :nuevo, line_name = :nombre
             WHERE report_id = 'P&L_DETAIL_OWNERS' AND line_code = :viejo
        """), {"viejo": viejo, "nuevo": nuevo, "nombre": nombre})
    for codigo, formula in CALCULOS.items():
        c.execute(sa.text("""
            UPDATE report_line_config SET calculation_logic = :f
             WHERE report_id = 'P&L_DETAIL_OWNERS' AND line_code = :c
        """), {"c": codigo, "f": formula})

    # 3. account_mapping: a que linea apunta cada regla.
    for viejo, (nuevo, nombre) in LINEAS.items():
        c.execute(sa.text("""
            UPDATE account_mapping
               SET report_line_code = :nuevo, report_line_name = :nombre
             WHERE report_id = 'P&L_DETAIL_OWNERS' AND report_line_code = :viejo
        """), {"viejo": viejo, "nuevo": nuevo, "nombre": nombre})

    # 3b. ⚠️ EL PASO CRITICO — ver el encabezado. Va ANTES del seed.
    for viejo, nuevo in DEPTOS.items():
        c.execute(sa.text("""
            UPDATE account_mapping SET source_department = :nuevo
             WHERE source_department = :viejo
        """), {"viejo": viejo, "nuevo": nuevo})

    # 3c. Los nombres de cuenta del GL que se ven en la plantilla de upload.
    for viejo, nuevo in (("Ingreso Innoceana", "Ingreso Rental #2"),
                         ("Ingreso Crowther Lab", "Ingreso Rental #3")):
        c.execute(sa.text("""
            UPDATE account_mapping
               SET account_name_example = replace(account_name_example, :viejo, :nuevo)
             WHERE account_name_example LIKE :patron
        """), {"viejo": viejo, "nuevo": nuevo, "patron": f"%{viejo}%"})

    # 4. P&L ya calculados, para que no queden con codigos inexistentes.
    for viejo, (nuevo, nombre) in LINEAS.items():
        c.execute(sa.text("""
            UPDATE pl_lines SET line_code = :nuevo, line_name = :nombre
             WHERE line_code = :viejo
        """), {"viejo": viejo, "nuevo": nuevo, "nombre": nombre})
    if sa.inspect(c).has_table("actual_pl_lines"):
        for viejo, (nuevo, _n) in LINEAS.items():
            c.execute(sa.text(
                "UPDATE actual_pl_lines SET line_code = :nuevo WHERE line_code = :viejo"
            ), {"viejo": viejo, "nuevo": nuevo})

    # 5. El catalogo de departamentos. `default_pl_group` cambia con el grupo;
    #    `is_revenue_dept` NO se toca — el 0156 sigue siendo cost-only, que es
    #    como estaba (ver COST_ONLY_GROUPS en seed_department_catalog).
    for dept, nombre in NOMBRES_DEPTO.items():
        c.execute(sa.text("""
            UPDATE department_catalog
               SET dept_name = :nombre,
                   default_pl_group = :grupo
             WHERE dept_code = :dept
        """), {"dept": dept, "nombre": nombre,
               "grupo": "RENTAL_2" if dept == "0155" else "RENTAL_3"})

    # 6. La nota del apagado, que nombraba departamentos que ya no existen.
    c.execute(sa.text("""
        UPDATE dept_enablement
           SET notes = 'Owner 2026-09-15: renombrado a Rental; sigue apagado'
         WHERE scope_key IN ('0155', '0156')
    """))


def downgrade() -> None:
    c = op.get_bind()
    for viejo, (nuevo, _n) in LINEAS.items():
        for tabla, col in (("report_line_config", "line_code"),
                           ("account_mapping", "report_line_code"),
                           ("pl_lines", "line_code")):
            c.execute(sa.text(
                f"UPDATE {tabla} SET {col} = :viejo WHERE {col} = :nuevo"
            ), {"viejo": viejo, "nuevo": nuevo})
    for viejo, nuevo in DEPTOS.items():
        c.execute(sa.text(
            "UPDATE account_mapping SET source_department = :viejo "
            "WHERE source_department = :nuevo"), {"viejo": viejo, "nuevo": nuevo})
    c.execute(sa.text("""
        UPDATE department_catalog SET dept_name = 'Innoceana',
               default_pl_group = 'INNOCEANA' WHERE dept_code = '0155'"""))
    c.execute(sa.text("""
        UPDATE department_catalog SET dept_name = 'Crowther Lab',
               default_pl_group = 'CROWTHER' WHERE dept_code = '0156'"""))
