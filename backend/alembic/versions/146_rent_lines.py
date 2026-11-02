"""Alquiler de locales: su tabla de contratos.

Revision ID: 146
Revises: 145
Create Date: 2026-11-01

El owner alquila locales dentro de la propiedad —hoy tres, en Sabor— y la renta
venía cayendo en las cuentas de Sabor Ojochal (4500/4501/4502 del 0155). No es
ingreso de Sabor: no tiene costo de venta ni sigue la ocupación del hotel.

Esta migración crea SOLO la tabla de contratos. El renglón del P&L (`REV_RENT`,
`OPEX_RENT`, `COS_RENT`, `PROFIT_RENT`), las 39 reglas de `account_mapping` del
depto 0157 y su fila en `department_catalog` NO van acá: viven en
`app/seed_data/mapping_pl.json` y en `seed_department_catalog`, que el Procfile
corre en el mismo deploy, justo después de `alembic upgrade head`. Escribirlas
también acá sería duplicar la verdad, y la regla del proyecto es al revés —el
seed manda sobre esas dos tablas y revierte lo que una migración le ponga encima.

⚠️ La renta YA facturada en 2026 sigue donde está (cuentas del 0155). Moverla
sin que el owner lo pida cambiaría un P&L ya cerrado; cuando lo pida, es un
UPDATE de `account_mapping` por (depto, cuenta), no de esta tabla.
"""
from alembic import op
import sqlalchemy as sa

revision = "146"
down_revision = "145"
branch_labels = None
depends_on = None

MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("rent_lines"):
        return
    op.create_table(
        "rent_lines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("ubicacion", sa.String(120), nullable=False, server_default=""),
        sa.Column("notes", sa.String(300), nullable=False, server_default=""),
        sa.Column("sort", sa.Integer, nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        *[sa.Column(m, sa.Numeric(14, 2), nullable=False, server_default="0")
          for m in MESES],
        sa.UniqueConstraint("scenario_id", "name", name="uq_rent_line_nombre"),
    )


def downgrade() -> None:
    op.drop_table("rent_lines")
