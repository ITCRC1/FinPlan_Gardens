"""0155 y 0205 se intercambian el nombre.

Revision ID: 143
Revises: 142
Create Date: 2026-10-07

    0205  Sabor de Ojochal  ->  Rental #1
    0155  Rental #2         ->  Sabor Ojochal

POR QUE EL INTERCAMBIO
======================
Owner, 2026-10-07, señalando la linea «Rental #2» del checkbook de ingresos:
«que este se llame SABOR OJOCHAL, en todos lados que aparezca».

El checkbook dibuja las lineas de `REVENUE_LINES`, y el 0155 tiene una —su
clave de dato sigue siendo `innoceana`, de cuando era Innoceana— mientras que
el 0205 nunca la tuvo: su ingreso entra por el mapeo de cuentas. Sin el
intercambio no habia donde digitar el ingreso de Sabor Ojochal mes a mes.

Por eso no queda ningun «Rental #2»: ese numero se lo llevo el nombre.

⚠️ EL ORDEN NO ES ARBITRARIO
============================
Primero se libera `SABOR_OJOCHAL` (0205 -> RENTAL_1) y recien despues el 0155
lo toma. Al reves, el UPDATE del 0155 chocaria contra `uq_report_line_code`,
porque la familia `SABOR_OJOCHAL` todavia existiria apuntando al 0205.

Y como siempre: `source_department` es parte de `uq_account_mapping`. El JSON ya
trae los nombres nuevos; si la base se quedara con los viejos, el seed leeria
las 69 reglas como nuevas y las insertaria al lado de las viejas — cada monto
contado dos veces, sin error y sin aviso. Cuarta vez que aparece esta trampa.
"""
from alembic import op
import sqlalchemy as sa

revision = "143"
down_revision = "142"
branch_labels = None
depends_on = None

#: (familia vieja, familia nueva). EN ESTE ORDEN.
PASOS = [("SABOR_OJOCHAL", "RENTAL_1"), ("RENTAL_2", "SABOR_OJOCHAL")]

PREFIJOS = ("REV_", "OPEX_", "COS_", "PROFIT_")


def _renombrar(c, viejo: str, nuevo: str) -> None:
    for pre in PREFIJOS:
        a, b = f"{pre}{viejo}", f"{pre}{nuevo}"
        # Si la nueva ya existiera (renombre a medias), la vieja sobra: se borra
        # primero, porque el UPDATE chocaria contra la restriccion unica.
        c.execute(sa.text("""
            DELETE FROM report_line_config
             WHERE report_id = 'P&L_DETAIL_OWNERS' AND line_code = :a
               AND EXISTS (SELECT 1 FROM report_line_config n
                            WHERE n.report_id = 'P&L_DETAIL_OWNERS'
                              AND n.line_code = :b)"""), {"a": a, "b": b})
        c.execute(sa.text(
            "UPDATE report_line_config SET line_code = :b "
            "WHERE report_id = 'P&L_DETAIL_OWNERS' AND line_code = :a"),
            {"a": a, "b": b})
        c.execute(sa.text(
            "UPDATE account_mapping SET report_line_code = :b "
            "WHERE report_id = 'P&L_DETAIL_OWNERS' AND report_line_code = :a"),
            {"a": a, "b": b})
        c.execute(sa.text(
            "UPDATE pl_lines SET line_code = :b WHERE line_code = :a"),
            {"a": a, "b": b})
        if sa.inspect(c).has_table("actual_pl_lines"):
            c.execute(sa.text(
                "UPDATE actual_pl_lines SET line_code = :b WHERE line_code = :a"),
                {"a": a, "b": b})
    # La formula de PROFIT_ nombra a las otras tres lineas.
    c.execute(sa.text(
        "UPDATE report_line_config "
        "SET calculation_logic = replace(calculation_logic, :a, :b) "
        "WHERE calculation_logic LIKE :p"),
        {"a": viejo, "b": nuevo, "p": f"%{viejo}%"})


def _textos(c, pares) -> None:
    for tabla, col in (("account_mapping", "report_line_name"),
                       ("account_mapping", "account_name_example"),
                       ("account_mapping", "source_department"),
                       ("account_mapping", "notes"),
                       ("report_line_config", "line_name"),
                       ("pl_lines", "line_name")):
        for viejo, nuevo in pares:
            c.execute(sa.text(
                f"UPDATE {tabla} SET {col} = replace({col}, :a, :b) "
                f"WHERE {col} LIKE :p"),
                {"a": viejo, "b": nuevo, "p": f"%{viejo}%"})


def upgrade() -> None:
    c = op.get_bind()

    for viejo, nuevo in PASOS:
        _renombrar(c, viejo, nuevo)

    # Los textos, en el MISMO orden y de la cadena mas larga a la mas corta.
    _textos(c, [
        ("Ingreso Sabor de Ojochal ", "Ingreso Rental #1 #"),
        ("Departamento de Sabor de Ojochal", "Departamento de Rental #1"),
        ("Sabor de Ojochal", "Rental #1"),
        ("Ingreso Rental #2 #", "Ingreso Sabor Ojochal #"),
        ("Departamento de Rental #2", "Departamento de Sabor Ojochal"),
        ("Rental #2", "Sabor Ojochal"),
    ])

    # El catalogo de departamentos y el grupo de cada uno.
    c.execute(sa.text("""
        UPDATE department_catalog
           SET dept_name = 'Rental #1', default_pl_group = 'RENTAL_1'
         WHERE dept_code = '0205'"""))
    c.execute(sa.text("""
        UPDATE department_catalog
           SET dept_name = 'Sabor Ojochal', default_pl_group = 'SABOR_OJOCHAL'
         WHERE dept_code = '0155'"""))

    # El nombre del depto viaja pegado a cada fila de planilla y gasto.
    for tabla in ("payroll_positions", "opex_entries", "cost_entries"):
        if not sa.inspect(c).has_table(tabla):
            continue
        if "dept_name" not in {x["name"] for x in sa.inspect(c).get_columns(tabla)}:
            continue
        c.execute(sa.text(
            f"UPDATE {tabla} SET dept_name = 'Rental #1' WHERE dept_code = '0205'"))
        c.execute(sa.text(
            f"UPDATE {tabla} SET dept_name = 'Sabor Ojochal' WHERE dept_code = '0155'"))


def downgrade() -> None:
    c = op.get_bind()
    for viejo, nuevo in [("SABOR_OJOCHAL", "RENTAL_2"), ("RENTAL_1", "SABOR_OJOCHAL")]:
        _renombrar(c, viejo, nuevo)
    _textos(c, [
        ("Ingreso Sabor Ojochal #", "Ingreso Rental #2 #"),
        ("Departamento de Sabor Ojochal", "Departamento de Rental #2"),
        ("Sabor Ojochal", "Rental #2"),
        ("Ingreso Rental #1 #", "Ingreso Sabor de Ojochal "),
        ("Departamento de Rental #1", "Departamento de Sabor de Ojochal"),
        ("Rental #1", "Sabor de Ojochal"),
    ])
    c.execute(sa.text("""
        UPDATE department_catalog
           SET dept_name = 'Sabor de Ojochal', default_pl_group = 'SABOR_OJOCHAL'
         WHERE dept_code = '0205'"""))
    c.execute(sa.text("""
        UPDATE department_catalog
           SET dept_name = 'Rental #2', default_pl_group = 'RENTAL_2'
         WHERE dept_code = '0155'"""))
