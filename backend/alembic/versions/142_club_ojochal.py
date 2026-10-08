"""Club Madresal pasa a llamarse Club Ojochal.

Revision ID: 142
Revises: 141
Create Date: 2026-10-07

Owner, 2026-10-07: que no aparezca «Madresal» en ningun lado de la app. El
departamento 260 es el mismo; cambia como se llama.

QUE NO CAMBIA
=============
Los CODIGOS de linea —`REV_CLUB`, `OPEX_CLUB`, `COS_CLUB`, `PROFIT_CLUB`— dicen
CLUB, no MADRESAL, asi que no hace falta renombrarlos. Tampoco el `dept_code`
260 ni el grupo `CLUB` del motor. Esto es solo rotulos y datos de texto, lo que
hace a esta migracion mucho mas chica que la 139 o la 140.

POR QUE HACE FALTA IGUAL
========================
⚠️ `source_department` («Departamento de Club Madresal») SI forma parte de
`uq_account_mapping`. El JSON ya trae el nombre nuevo: si la base se quedara con
el viejo, el seed leeria las 54 reglas como NUEVAS —llave distinta— y las
insertaria al lado de las viejas. Serian 108 reglas para 54 cuentas y cada monto
entraria DOS VECES al P&L, sin error y sin aviso.

El orden lo garantiza el Procfile: `alembic upgrade head` corre antes que
`python -m app.seed`.
"""
from alembic import op
import sqlalchemy as sa

revision = "142"
down_revision = "141"
branch_labels = None
depends_on = None


def upgrade() -> None:
    c = op.get_bind()

    # 1. ⚠️ EL PASO CRITICO. Va antes del seed; ver el encabezado.
    c.execute(sa.text("""
        UPDATE account_mapping
           SET source_department = 'Departamento de Club Ojochal'
         WHERE source_department = 'Departamento de Club Madresal'
    """))

    # 2. Rotulos del mapeo y de la configuracion de lineas.
    for tabla, col in (("account_mapping", "report_line_name"),
                       ("account_mapping", "account_name_example"),
                       ("account_mapping", "notes"),
                       ("report_line_config", "line_name"),
                       ("pl_lines", "line_name")):
        c.execute(sa.text(f"""
            UPDATE {tabla}
               SET {col} = replace(replace({col},
                       'Ingreso Madresal Club', 'Ingreso Club Ojochal'),
                       'Club Madresal', 'Club Ojochal')
             WHERE {col} LIKE '%Madresal%'
        """))

    # 3. El catalogo de departamentos. El seed lo re-afirma en cada deploy;
    #    esto lo deja bien ya, sin esperar al arranque.
    c.execute(sa.text("""
        UPDATE department_catalog SET dept_name = 'Club Ojochal'
         WHERE dept_code = '260'
    """))

    # 4. El nombre del depto que viaja pegado a cada fila de planilla y de gasto.
    for tabla in ("payroll_positions", "opex_entries", "cost_entries"):
        if not sa.inspect(c).has_table(tabla):
            continue
        cols = {x["name"] for x in sa.inspect(c).get_columns(tabla)}
        if "dept_name" in cols:
            c.execute(sa.text(
                f"UPDATE {tabla} SET dept_name = 'Club Ojochal' "
                f"WHERE dept_code = '260'"))

    # 5. El break-even trae el nombre en su propia semilla.
    if sa.inspect(c).has_table("break_even_departamentos"):
        cols = {x["name"] for x in sa.inspect(c).get_columns("break_even_departamentos")}
        if "nombre" in cols:
            c.execute(sa.text(
                "UPDATE break_even_departamentos SET nombre = 'Club Ojochal' "
                "WHERE nombre = 'Club Madresal'"))


def downgrade() -> None:
    c = op.get_bind()
    c.execute(sa.text("""
        UPDATE account_mapping
           SET source_department = 'Departamento de Club Madresal'
         WHERE source_department = 'Departamento de Club Ojochal'
    """))
    for tabla, col in (("account_mapping", "report_line_name"),
                       ("account_mapping", "account_name_example"),
                       ("account_mapping", "notes"),
                       ("report_line_config", "line_name"),
                       ("pl_lines", "line_name")):
        c.execute(sa.text(f"""
            UPDATE {tabla}
               SET {col} = replace(replace({col},
                       'Ingreso Club Ojochal', 'Ingreso Madresal Club'),
                       'Club Ojochal', 'Club Madresal')
             WHERE {col} LIKE '%Ojochal%'
        """))
    c.execute(sa.text("""
        UPDATE department_catalog SET dept_name = 'Club Madresal'
         WHERE dept_code = '260'
    """))
