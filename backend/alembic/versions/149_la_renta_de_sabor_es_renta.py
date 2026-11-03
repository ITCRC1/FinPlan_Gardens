"""La renta del 0155 va a `REV_RENT`. (El trabajo lo hace el seed.)

Revision ID: 149
Revises: 148
Create Date: 2026-11-02

Owner, 2026-11-02: «no hay restaurantes en ojochal» · «es alquiler de locales
restaurantes solamente».

Esta migración **no hace nada**, y se conserva por dos razones: la base de
producción quedó marcada en 149 (borrar el archivo deja `alembic upgrade head`
sin poder ubicar la revisión), y la historia de abajo vale más escrita que
perdida.

## El cambio

El depto 0155 venía del linaje de clones modelado como un restaurante entero
—ingreso 4500/4501/4502, costo 5500/5501, planilla 6000-6030, opex 7xxx— y su
ingreso caía en `REV_SABOR_OJOCHAL`. La pista de que algo no cerraba estuvo
siempre a la vista: **el 0155 nunca tuvo un colón de costo, planilla ni opex en
ningún escenario**. Sólo ingreso, que es justo lo que se ve cuando lo único que
pasa es que se cobra una renta.

Vive en `app/seed_data/mapping_pl.json`, que es quien manda sobre
`account_mapping`. Una migración que lo escribiera acá se revertiría sola.

## El primer intento falló, y vale la pena saber por qué

La versión original de esta migración SÍ hacía el `UPDATE`. Se desplegó, y en
producción los $64.661,42 de 2026 y los $108.628,67 de 2025 **desaparecieron de
los dos renglones**: ni en Sabor Ojochal ni en Rent. El ingreso del ACTUAL 2026
bajó de $222.037,87 a $157.376,45.

El motor sólo emite las líneas que existen en `report_line_config`, y
**`REV_RENT` no estaba en la base**: 119 de las 123 del archivo sí, las cuatro
de Rent no. El mapeo apuntaba a un renglón inexistente, así que la plata entraba
a `TOTAL_REVENUES` —`SUM(REV_*)` la toma de `line_amounts` igual— y no se
dibujaba en ninguna fila.

¿Y por qué faltaban? Porque **el seed del mapeo se venía cayendo entero en cada
despliegue desde septiembre**, por una sola fila repetida (el 7310 de Tours; ver
`app/seed_mapping.py::_clave_ocupada_mapeo`). El `commit` es uno solo al final
de las dos siembras, así que esa excepción revertía el lote completo. El
arranque la dejaba en una línea de log y seguía.

Arreglado el seed, las cuatro líneas entraron y el cambio se aplica solo. Medido
contra producción antes de reaplicarlo: el ingreso se mueve de renglón y
`TOTAL_REVENUES` **no cambia ni un centavo**, en 2025 y en 2026.

## La lección, que es la cara

Un mapeo que apunta a un renglón inexistente no falla: suma al total y no se
dibuja. Y un seed que no puede confirmar tampoco falla: imprime una línea y
sigue. Los dos silencios juntos esconden plata durante meses con el total
cuadrando. Por eso ahora hay pruebas para ambos —
`tests/test_el_seed_no_se_tumba_solo.py` y
`test_pl_detail_tres_ambitos.py::test_ninguna_linea_operativa_se_queda_sin_fila`.
"""

revision = "149"
down_revision = "148"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Sin efecto: el mapeo lo re-afirma el seed desde `mapping_pl.json`."""


def downgrade() -> None:
    pass
