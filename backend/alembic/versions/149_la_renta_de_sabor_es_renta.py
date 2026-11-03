"""(REVERTIDA) Mandar la renta del 0155 a `REV_RENT` no alcanza.

Revision ID: 149
Revises: 148
Create Date: 2026-11-02

Esta migración **ya no hace nada**, y el archivo se conserva sólo para no
romper la cadena de Alembic: la base de producción alcanzó a quedar marcada en
149 antes de que se revirtiera, y borrar el archivo deja `alembic upgrade head`
sin poder ubicar la revisión.

QUÉ INTENTABA
Owner, 2026-11-02: «no hay restaurantes en ojochal» · «es alquiler de locales
restaurantes solamente». El ingreso del depto 0155 debía pasar de
`REV_SABOR_OJOCHAL` a `REV_RENT`, por (departamento, cuenta).

POR QUÉ NO ALCANZÓ — y por qué se vio sólo en producción
Cambiar `account_mapping` mueve el ingreso **del detalle del mayor**. Pero el
P&L de un ACTUAL no sale siempre de ahí: `_compute_pl_month_core` prefiere el
resumen por línea que se importó (`actual_pl_lines`), y sólo baja al detalle si
`_detalle_fino_si_cuadra` confirma que los dos dan lo mismo. Al mover la cuenta
de renglón, el detalle dejó de cuadrar contra el resumen —que sigue trayendo la
plata en la línea vieja— y el guardián se quedó con el resumen.

Resultado medido en producción: los $64.661,42 de 2026 y los $108.628,67 de
2025 **desaparecieron de los dos renglones**. Ni en Sabor Ojochal ni en Rent.
Y el total de ingresos del ACTUAL 2026 bajó de $222.037,87 a $157.376,45.

Ningún test lo atrapó porque todos corren sobre el mapeo y la plantilla; el
desvío por el resumen importado sólo aparece con un ACTUAL que tenga resumen
cargado, que es justo lo que no hay en la suite.

LO QUE FALTA, cuando se retome: mover también el resumen por línea del ACTUAL
(o decidir que para estos escenarios manda el detalle), y recién entonces el
mapeo. El mapeo solo deja la plata en el aire.
"""

revision = "149"
down_revision = "148"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Revertida: el seed deja el mapeo en `REV_SABOR_OJOCHAL`."""


def downgrade() -> None:
    pass
