"""El rotulo de origen del mapeo dice lo mismo que la clase de la cuenta.

Port de CWL (163), owner 2026-11-10: «asegurate que 4 son ingresos, 5 costos,
6 planilla, 7 opex y 8 gastos de la propiedad y 9 stats».

El calculo ya separa por el primer digito de la cuenta (`pl_engine`); lo que no
calzaba era `source_origin`, una etiqueta que ningun calculo lee: en Ojochal
103 filas decian «Cost», «Opex», «Payroll» o «Revenue» contra su clase
(planilla de Lavanderia y de Utility, OPEX de once deptos como «Cost», Rent y
Rental #1 como «Revenue», dos como «Payroll»). Quedan clase 6 = Payroll y
clase 7 = Opex. Las clases 4, 5 y 8 ya decian lo suyo.

⚠️ `source_origin` es parte de la LLAVE de la semilla (uq_account_mapping). Si
solo se cambiara `mapping_pl.json`, la semilla insertaria las filas nuevas y las
viejas quedarian al lado: dos reglas para el mismo (depto, cuenta). Por eso esta
migracion renombra EN EL LUGAR, antes de que la semilla corra. Ninguna fila
nueva choca con una existente (verificado contra la base: 0 colisiones).

Revision ID: 150
Revises: 149
"""
import sqlalchemy as sa
from alembic import op

revision = "150"
down_revision = "149"
branch_labels = None
depends_on = None

#: (report_id, source_department, account_code, origen viejo, origen nuevo)
CAMBIOS = [
    ('P&L_DETAIL_OWNERS', 'Departamento de Ventas y Mercadeo', '7000', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Ventas y Mercadeo', '7070', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Spa', '7250', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Spa', '7080', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Spa', '7085', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Spa', '7090', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Spa', '7095', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Spa', '7245', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Spa', '7255', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Spa', '7485', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Rental #1', '7105', 'Revenue', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Rental #1', '7110', 'Revenue', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Rental #1', '7150', 'Revenue', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Rental #1', '7175', 'Revenue', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Rental #1', '7185', 'Revenue', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Utility', '6000', 'Opex', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Utility', '6001', 'Opex', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Utility', '6002', 'Opex', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Utility', '6003', 'Opex', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Utility', '6004', 'Opex', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Utility', '6010', 'Opex', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Utility', '6020', 'Opex', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Utility', '6021', 'Opex', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Utility', '6022', 'Opex', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Utility', '6023', 'Opex', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Utility', '6024', 'Opex', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Utility', '6025', 'Opex', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Utility', '6026', 'Opex', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Utility', '6027', 'Opex', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Utility', '6028', 'Opex', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Utility', '6029', 'Opex', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Utility', '6030', 'Opex', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Departamento Tienda 0151', '7105', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento Tienda 0151', '7110', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento Tienda 0151', '7150', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento Tienda 0151', '7175', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento Tienda 0151', '7185', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento Gift Shop', '7105', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento Gift Shop', '7110', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento Gift Shop', '7150', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento Gift Shop', '7175', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento Gift Shop', '7185', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento Private Bar', '7105', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento Private Bar', '7110', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento Private Bar', '7150', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento Private Bar', '7175', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento Private Bar', '7185', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Tours', '7105', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Tours', '7110', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Tours', '7150', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Tours', '7175', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Tours', '7185', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Tours', '7310', 'Payroll', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Transportation', '7105', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Transportation', '7110', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Transportation', '7150', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Transportation', '7175', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Transportation', '7185', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Sabor Ojochal', '7110', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Sabor Ojochal', '7150', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Sabor Ojochal', '7175', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Sabor Ojochal', '7185', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento Rental #3', '7105', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento Rental #3', '7110', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento Rental #3', '7150', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento Rental #3', '7175', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento Rental #3', '7185', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Laundry Revenue', '6000', 'Cost', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Laundry Revenue', '6001', 'Cost', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Laundry Revenue', '6002', 'Cost', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Laundry Revenue', '6003', 'Cost', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Laundry Revenue', '6004', 'Cost', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Laundry Revenue', '6010', 'Cost', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Laundry Revenue', '6020', 'Cost', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Laundry Revenue', '6021', 'Cost', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Laundry Revenue', '6022', 'Cost', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Laundry Revenue', '6023', 'Cost', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Laundry Revenue', '6024', 'Cost', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Laundry Revenue', '6025', 'Cost', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Laundry Revenue', '6026', 'Cost', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Laundry Revenue', '6027', 'Cost', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Laundry Revenue', '6028', 'Cost', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Laundry Revenue', '6029', 'Cost', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Laundry Revenue', '6030', 'Cost', 'Payroll'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Ventas y Mercadeo', '7680', 'Payroll', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de TI', '7105', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Club Ojochal', '7110', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Club Ojochal', '7150', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Club Ojochal', '7185', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Club Ojochal', '7665', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Club Ojochal', '7670', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Club Ojochal', '7675', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Club Ojochal', '7685', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Área Recreativa', '7105', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Área Recreativa', '7110', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Área Recreativa', '7150', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Área Recreativa', '7175', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Área Recreativa', '7185', 'Cost', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Rent', '7105', 'Revenue', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Rent', '7110', 'Revenue', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Rent', '7150', 'Revenue', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Rent', '7175', 'Revenue', 'Opex'),
    ('P&L_DETAIL_OWNERS', 'Departamento de Rent', '7185', 'Revenue', 'Opex'),
]

_SQL = sa.text(
    "UPDATE account_mapping SET source_origin = :nuevo "
    "WHERE report_id = :rep AND source_department = :dep AND account_code = :cta "
    "AND source_origin = :viejo AND vigente_desde IS NULL")


def upgrade() -> None:
    con = op.get_bind()
    for rep, dep, cta, viejo, nuevo in CAMBIOS:
        con.execute(_SQL, {"rep": rep, "dep": dep, "cta": cta, "viejo": viejo, "nuevo": nuevo})


def downgrade() -> None:
    con = op.get_bind()
    for rep, dep, cta, viejo, nuevo in CAMBIOS:
        con.execute(_SQL, {"rep": rep, "dep": dep, "cta": cta, "viejo": nuevo, "nuevo": viejo})
