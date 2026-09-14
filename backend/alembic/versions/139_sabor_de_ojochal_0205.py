"""0205 pasa de «Claro del Bosque (Huerta)» a «Sabor de Ojochal» y de overhead
solo-gastos a departamento operativo con ingreso.

Revision ID: 139_sabor_de_ojochal_0205
Revises: 138_tab_enablement_por_perfil
Create Date: 2026-09-14

POR QUÉ HACE FALTA UNA MIGRACIÓN Y NO ALCANZA EL SEED
=====================================================
El seed (`app/seed_mapping.py`) busca las filas por su LLAVE DE NEGOCIO:

    report_line_config  →  (report_id, line_code)
    account_mapping     →  (report_id, source_department, account_code,
                            source_origin, vigente_desde)

Al renombrar `line_code`, las cuatro líneas del 0205 cambian de llave: el seed
inserta las nuevas y **deja las viejas donde están** — no borra por ausencia, a
propósito (borrar le vaciaría el P&L a un hotel con mapeos propios). Sin este
`delete`, `OH_/COH_/REV_/PROFIT_CLARO_HUERTA` quedarían activas y huérfanas, y
el reporte dibujaría las dos versiones del mismo departamento.

`account_mapping` NO tiene ese problema: `report_line_code` no forma parte de su
llave, así que el seed lo actualiza en su lugar. Igual se actualiza acá para que
la base quede correcta ANTES del primer arranque, y no dependa del orden en que
corran `alembic` y el seed.

⚠️ `source_department` TAMBIÉN cambia, y por eso hay que mirarlo dos veces: sí
forma parte de `uq_account_mapping`. El paso 3b lo actualiza en la base ANTES de
que corra el seed; si no, el seed leería las 39 filas del JSON como nuevas y las
insertaría al lado de las viejas —78 reglas para 39 cuentas, cada monto contado
dos veces en el P&L, sin error y sin aviso—. El orden lo garantiza el Procfile.

Es el nombre del departamento tal como viene en el archivo que se sube. No se
usa para machear el archivo contra el mapeo (de eso se encarga la tabla de
alias de `gl_detail_importer`, donde «sabor» y «claro» apuntan los dos al
0205): se usa para derivar el `dept_code`, y por el alias sigue dando 0205.
"""
from alembic import op
import sqlalchemy as sa

revision = "139"
down_revision = "138"
branch_labels = None
depends_on = None

RENOMBRES = [
    ("REV_CLARO_HUERTA", "REV_SABOR_OJOCHAL", "REVENUES",
     "SEC_REVENUES", "Sabor de Ojochal", "MAPPED", "SUM mapped accounts", 27),
    ("OH_CLARO_HUERTA", "OPEX_SABOR_OJOCHAL", "OPERATING EXPENSES",
     "SEC_OPERATING_EXPENSES", "Sabor de Ojochal", "MAPPED",
     "Cost + Payroll + Opex", 46),
    ("COH_CLARO_HUERTA", "COS_SABOR_OJOCHAL", "COST OF SALES",
     "SEC_OPERATING_EXPENSES", "Sabor de Ojochal Cost", "MAPPED",
     "SUM mapped accounts", 47),
    ("PROFIT_CLARO_HUERTA", "PROFIT_SABOR_OJOCHAL", "OPERATING PROFIT",
     "SEC_OPERATING_PROFIT", "Sabor de Ojochal", "CALCULATED",
     "REV_SABOR_OJOCHAL - OPEX_SABOR_OJOCHAL - COS_SABOR_OJOCHAL", 61),
]


def upgrade() -> None:
    c = op.get_bind()

    # 1. Si una instalación ya tuviera AMBAS (un deploy que sembró las nuevas
    #    antes de esta migración), la vieja sobra. Se borra PRIMERO: si se
    #    intentara renombrar con la nueva ya presente, el UPDATE chocaría contra
    #    `uq_report_line_code` y la migración entera se caería.
    for viejo, nuevo, *_ in RENOMBRES:
        c.execute(sa.text("""
            DELETE FROM report_line_config
             WHERE report_id = 'P&L_DETAIL_OWNERS' AND line_code = :viejo
               AND EXISTS (SELECT 1 FROM report_line_config n
                            WHERE n.report_id = 'P&L_DETAIL_OWNERS'
                              AND n.line_code = :nuevo)
        """), {"viejo": viejo, "nuevo": nuevo})

    # 2. report_line_config — renombrar en su lugar. Se actualiza en vez de
    #    borrar+insertar para no perder el `id`, al que puede apuntar dato ajeno.
    for viejo, nuevo, sec, padre, nombre, tipo, calc, orden in RENOMBRES:
        c.execute(sa.text("""
            UPDATE report_line_config
               SET line_code = :nuevo, section = :sec, parent_line_code = :padre,
                   line_name = :nombre, line_type = :tipo,
                   calculation_logic = :calc, display_order = :orden
             WHERE report_id = 'P&L_DETAIL_OWNERS' AND line_code = :viejo
        """), {"viejo": viejo, "nuevo": nuevo, "sec": sec, "padre": padre,
               "nombre": nombre, "tipo": tipo, "calc": calc, "orden": orden})

    # 3. account_mapping — las 39 reglas apuntan al código nuevo.
    for viejo, nuevo, sec, _padre, nombre, _tipo, _calc, orden in RENOMBRES:
        c.execute(sa.text("""
            UPDATE account_mapping
               SET report_line_code = :nuevo, report_line_name = :nombre,
                   report_section = :sec, display_order = :orden
             WHERE report_id = 'P&L_DETAIL_OWNERS' AND report_line_code = :viejo
        """), {"viejo": viejo, "nuevo": nuevo, "nombre": nombre,
               "sec": sec, "orden": orden})

    # 3b. ⚠️ `source_department` — el nombre del departamento tal como viene en
    #     el archivo que se sube. ESTE UPDATE ES OBLIGATORIO Y VA ANTES DEL SEED.
    #
    #     `source_department` SÍ forma parte de `uq_account_mapping`. El JSON ya
    #     dice «Departamento de Sabor de Ojochal»: si la base se quedara con el
    #     nombre viejo, el seed vería las 39 filas del archivo como NUEVAS —
    #     llave distinta— y las INSERTARÍA al lado de las viejas. Serían 78
    #     reglas para 39 cuentas y cada uno de esos montos entraría DOS VECES al
    #     P&L, sin error y sin aviso.
    #
    #     El orden lo garantiza el Procfile: `alembic upgrade head` corre antes
    #     que `python -m app.seed`.
    c.execute(sa.text("""
        UPDATE account_mapping
           SET source_department = 'Departamento de Sabor de Ojochal'
         WHERE source_department = 'Departamento de Claro Huerta'
    """))
    c.execute(sa.text("""
        UPDATE account_mapping
           SET account_name_example = replace(account_name_example,
                                              'Claro Huerta', 'Sabor de Ojochal')
         WHERE account_name_example LIKE '%Claro Huerta%'
    """))

    # 4. pl_lines ya calculadas: mismo renombre, para que un P&L guardado no
    #    quede con códigos que ya no existen en la configuración.
    for viejo, nuevo, *_ in RENOMBRES:
        c.execute(sa.text("""
            UPDATE pl_lines SET line_code = :nuevo, line_name = :nombre
             WHERE line_code = :viejo
        """), {"viejo": viejo, "nuevo": nuevo,
               "nombre": "Sabor de Ojochal"})

    # 5. actual_pl_lines (snapshot de actuales importados), si existe la tabla.
    if sa.inspect(c).has_table("actual_pl_lines"):
        for viejo, nuevo, *_ in RENOMBRES:
            c.execute(sa.text(
                "UPDATE actual_pl_lines SET line_code = :nuevo WHERE line_code = :viejo"
            ), {"viejo": viejo, "nuevo": nuevo})

    # 6. El catálogo de departamentos. El seed lo re-afirma en cada deploy, pero
    #    esto lo deja bien YA, sin esperar al arranque.
    c.execute(sa.text("""
        UPDATE department_catalog
           SET dept_name = 'Sabor de Ojochal', name_en = '',
               default_pl_group = 'SABOR_OJOCHAL', pl_kind = 'OPERATING',
               is_revenue_dept = true, usali_class = NULL
         WHERE dept_code = '0205'
    """))

    # 7. Encender el 0205 para esta propiedad. Estaba apagado en las cinco
    #    dimensiones («Owner 2026-09-08: esta propiedad no opera este
    #    departamento») — con el cambio de destino sí lo opera, y apagado no se
    #    vería ni aunque tuviera plata.
    c.execute(sa.text("UPDATE dept_enablement SET enabled = true, "
                      "notes = 'Owner 2026-09-14: reabierto como Sabor de Ojochal' "
                      "WHERE scope_key = '0205'"))


def downgrade() -> None:
    c = op.get_bind()
    for viejo, nuevo, *_ in RENOMBRES:
        for tabla, col in (("report_line_config", "line_code"),
                           ("account_mapping", "report_line_code"),
                           ("pl_lines", "line_code")):
            c.execute(sa.text(
                f"UPDATE {tabla} SET {col} = :viejo WHERE {col} = :nuevo"
            ), {"viejo": viejo, "nuevo": nuevo})
    c.execute(sa.text("""
        UPDATE department_catalog
           SET dept_name = 'Claro del Bosque (Huerta)',
               name_en = 'Claro del Bosque (Garden)',
               default_pl_group = 'OTHER_OVERHEAD', pl_kind = 'OVERHEAD',
               is_revenue_dept = false, usali_class = 7
         WHERE dept_code = '0205'
    """))
    c.execute(sa.text("""
        UPDATE account_mapping
           SET source_department = 'Departamento de Claro Huerta'
         WHERE source_department = 'Departamento de Sabor de Ojochal'
    """))
    c.execute(sa.text("UPDATE dept_enablement SET enabled = false "
                      "WHERE scope_key = '0205'"))
