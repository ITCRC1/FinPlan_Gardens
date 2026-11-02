"""Cada contrato de alquiler elige SU cuenta contable.

Revision ID: 147
Revises: 146
Create Date: 2026-11-01

Owner, 2026-11-01: «asocia estas cuentas internamente para que se escojan» ·
«podés agregar más cuentas como opción para poder meter más alquileres en el
futuro».

Sin esto los contratos sumaban a `REV_RENT` en bloque y el mayor no podía
cotejarse inquilino por inquilino: en el P&L el total cuadraba, pero el detalle
por cuenta mostraba un bulto donde la contabilidad tiene un renglón por local.

La LISTA de cuentas no va acá: sale de `account_mapping` (depto 0157), que el
seed siembra desde `mapping_pl.json` con el rango 4520-4535. Así, el día que
hagan falta más, es una regla nueva desde Admin → Account Mapping y no un
cambio de código. El seed manda sobre esa tabla; una migración que la escriba
se revierte sola en el próximo deploy.
"""
from alembic import op
import sqlalchemy as sa

revision = "147"
down_revision = "146"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("rent_lines")}
    if "account_code" not in cols:
        op.add_column("rent_lines", sa.Column(
            "account_code", sa.String(10), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("rent_lines", "account_code")
