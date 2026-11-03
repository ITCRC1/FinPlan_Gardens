"""Lo que el mayor llama «Sabor Ojochal» es alquiler de locales.

Revision ID: 149
Revises: 148
Create Date: 2026-11-02

Owner, 2026-11-02: «no hay restaurantes en ojochal» · «es alquiler de locales
restaurantes solamente».

QUÉ PASABA
El depto 0155 venía del linaje de clones modelado como un restaurante entero
—ingreso 4500/4501/4502, costo de venta 5500/5501, planilla 6000-6030 y opex
7xxx—, y su ingreso caía en el renglón `REV_SABOR_OJOCHAL`, que Hotel
Consolidation rotula «Restaurantes externos». Pero el hotel no opera ningún
restaurante: alquila los locales. Por eso el 0155 **nunca tuvo un solo colón de
costo, planilla ni opex** en ningún escenario: sólo ingreso, que es justo lo que
se ve cuando se cobra una renta.

El total del P&L siempre cuadró —por eso nadie lo notó— pero la plata estaba en
el renglón equivocado, y partida en dos: la renta de 2025 y 2026 en «Sabor
Ojochal» y la de 2027 en «Rent» (los cuatro contratos del módulo de alquileres,
depto 0157). Dos renglones para la misma cosa no se pueden comparar año contra
año, que es exactamente lo que el consolidado necesita hacer.

QUÉ HACE
Manda el ingreso del 0155 a `REV_RENT`, por (departamento, cuenta). Es el UPDATE
que la migración 146 dejó anotado para cuando el owner lo pidiera:

    «⚠️ La renta YA facturada en 2026 sigue donde está (cuentas del 0155).
      Moverla sin que el owner lo pida cambiaría un P&L ya cerrado; cuando lo
      pida, es un UPDATE de `account_mapping` por (depto, cuenta).»

Mueve plata real de meses cerrados: 2025 $108,628.67 · 2026 ene-jul $64,661.42 ·
proyección ago-dic del forecast $34,640.05. No cambia ningún total: sale de un
renglón de ingreso y entra en otro.

LA CUENTA NO SE TOCA
Las filas del mayor siguen en 4500/0155 con su nombre original. Renombrarlas
rompería la trazabilidad contra la contabilidad, que es de donde salieron. Lo
que cambia es a qué renglón del reporte suman. Los contratos nuevos sí usan el
rango 4520-4535 del 0157, así que el detalle por cuenta muestra el origen real
de cada año — que es la idea.

⚠️ EL SEED MANDA SOBRE ESTA TABLA. Esta migración sola se revertiría en el
próximo despliegue. El cambio de verdad vive en `app/seed_data/mapping_pl.json`
(las tres filas de ingreso del 0155) y esta migración sólo lo adelanta a la base
actual. Las dos cosas van juntas o ninguna sirve.

Blindado por `tests/test_la_renta_no_es_restaurante.py`.
"""
from alembic import op
import sqlalchemy as sa

revision = "149"
down_revision = "148"
branch_labels = None
depends_on = None

DEPTO = "Departamento de Sabor Ojochal"
NOTA = ("Alquiler de locales, no operacion de restaurante: el owner confirmo "
        "2026-11-02 que en Ojochal no hay restaurante propio. El mayor lo "
        "sigue llamando «Ingreso Sabor Ojochal» por arrastre del catalogo; "
        "el renglon del P&L es Rent, igual que los contratos del 0157.")


def _mover(desde: str, hacia: str, nombre: str, orden: int, nota) -> None:
    op.get_bind().execute(sa.text("""
        UPDATE account_mapping
           SET report_line_code = :hacia,
               report_line_name = :nombre,
               display_order    = :orden,
               notes            = :nota
         WHERE source_department = :depto
           AND lower(source_origin) = 'revenue'
           AND report_line_code = :desde
    """), {"desde": desde, "hacia": hacia, "nombre": nombre,
           "orden": orden, "nota": nota, "depto": DEPTO})


def upgrade() -> None:
    _mover("REV_SABOR_OJOCHAL", "REV_RENT", "Rent", 28, NOTA)


def downgrade() -> None:
    _mover("REV_RENT", "REV_SABOR_OJOCHAL", "Sabor Ojochal", 27, None)
