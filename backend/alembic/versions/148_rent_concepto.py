"""Un inquilino tiene un SET de cuentas, no una.

Revision ID: 148
Revises: 147
Create Date: 2026-11-01

Owner, 2026-11-01: «no quiero solo una cuenta, quiero un set de cuentas». Un
local no paga una sola cosa — alquiler, mantenimiento, servicios — y cada
concepto va a su cuenta contable.

La fila pasa de ser (inquilino) a ser (inquilino, concepto). Lo que ya estaba
cargado se vuelve el concepto «Alquiler», que es lo que era.

⚠️ El unique viejo era (scenario_id, name): con el concepto nuevo prohibiría
justamente lo que se viene a permitir —dos filas del mismo inquilino—, así que
se reemplaza por (scenario_id, name, concepto). Si no se cambia, agregar el
segundo concepto revienta con un 500 de integridad.
"""
from alembic import op
import sqlalchemy as sa

revision = "148"
down_revision = "147"
branch_labels = None
depends_on = None

VIEJO = "uq_rent_line_nombre"
NUEVO = "uq_rent_line_concepto"


def upgrade() -> None:
    c = op.get_bind()
    insp = sa.inspect(c)
    cols = {x["name"] for x in insp.get_columns("rent_lines")}
    if "concepto" not in cols:
        op.add_column("rent_lines", sa.Column(
            "concepto", sa.String(80), nullable=False, server_default="Alquiler"))
    uniques = {u["name"] for u in insp.get_unique_constraints("rent_lines")}
    if VIEJO in uniques:
        op.drop_constraint(VIEJO, "rent_lines", type_="unique")
    if NUEVO not in uniques:
        op.create_unique_constraint(
            NUEVO, "rent_lines", ["scenario_id", "name", "concepto"])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    uniques = {u["name"] for u in insp.get_unique_constraints("rent_lines")}
    if NUEVO in uniques:
        op.drop_constraint(NUEVO, "rent_lines", type_="unique")
    # Al volver, dos conceptos del mismo inquilino chocarian con el unique
    # viejo. Se deja el mas chico vivo y se borran los demas.
    op.execute(sa.text("""
        DELETE FROM rent_lines a USING rent_lines b
         WHERE a.scenario_id = b.scenario_id AND a.name = b.name AND a.id > b.id
    """))
    op.create_unique_constraint(VIEJO, "rent_lines", ["scenario_id", "name"])
    op.drop_column("rent_lines", "concepto")
