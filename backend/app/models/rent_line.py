# -*- coding: utf-8 -*-
"""Los locales que Ojochal Gardens alquila — una fila por inquilino.

El alquiler NO es ingreso de Sabor Ojochal. Los inquilinos ocupan espacio
dentro de Sabor, y por eso venían cayendo en sus tres cuentas (4500/4501/4502
del depto 0155), pero lo que entra es renta: no tiene costo de venta, no sigue
la ocupación del hotel, y el owner lo quiere ver aparte. Desde acá sale su
propio renglón del P&L (`REV_RENT`, depto 0157).

**Por qué una tabla y no tres líneas de `RevenueEntry`.** Los inquilinos entran
y salen: hoy son tres, el mes que viene cuatro. Una línea fija por inquilino
obligaría a un cambio de código y un deploy cada vez que se firma un contrato.
Acá el owner agrega la fila desde la pantalla y la suma de las filas activas es
la que viaja al P&L, por `persistir_ingreso_de_driver`, igual que el Club.

**Una fila es (inquilino, concepto), no (inquilino).** Un local no paga una sola
cosa: alquiler, mantenimiento, servicios, cada uno a su cuenta (owner,
2026-11-01: «no quiero solo una cuenta, quiero un set de cuentas»). El inquilino
es el conjunto de sus filas y la pantalla las agrupa por nombre.

⚠️ **Por qué el concepto NO vive en una tabla hija.** La copia de escenario
(`_clone_scenario_data`) recorre los modelos con `scenario_id` y le da un UUID
nuevo a cada fila — pero NO reapunta llaves foráneas. Una tabla hija colgando de
`rent_lines.id` se copiaría apuntando al contrato del escenario ORIGEN: el
Budget copiado mostraría los conceptos del otro escenario, o ninguno, sin dar
error. Plana, la copia funciona sola.

El precio es que el nombre del inquilino se repite por fila. La pantalla lo
edita UNA vez por grupo y lo escribe en todas, así que no se despega.
"""
import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]


class RentLine(Base):
    """Un contrato de alquiler × escenario, con sus doce meses en USD."""

    __tablename__ = "rent_lines"
    __table_args__ = (
        # El mismo concepto dos veces para el mismo inquilino es un error de
        # digitación, no dos cobros: el segundo pisaría al primero en cualquier
        # reporte que agrupe. Distintos conceptos del mismo inquilino SÍ —es
        # justamente el set de cuentas.
        UniqueConstraint("scenario_id", "name", "concepto",
                         name="uq_rent_line_concepto"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)

    name: Mapped[str] = mapped_column(String(120))
    #: Qué se cobra: «Alquiler», «Mantenimiento», «Servicios»… Un inquilino
    #: tiene una fila por concepto, cada una con su cuenta y sus doce meses.
    concepto: Mapped[str] = mapped_column(String(80), default="Alquiler")
    #: Dónde está el local. Texto libre: «Sabor», «Lobby», «Área Recreativa».
    ubicacion: Mapped[str] = mapped_column(String(120), default="")
    #: La cuenta contable del contrato, de las del depto 0157 (4520-4535). Se
    #: ELIGE, no se escribe: la lista sale de `account_mapping`, así que agregar
    #: una cuenta nueva es una regla en Admin y no un cambio de código.
    #:
    #: Vacía se permite a propósito —un contrato se negocia antes de que
    #: contabilidad abra su cuenta— y en ese caso la renta igual suma al P&L por
    #: la línea Rent; lo que no se puede es cotejarla contra el mayor.
    account_code: Mapped[str] = mapped_column(String(10), default="")
    notes: Mapped[str] = mapped_column(String(300), default="")
    #: Orden en pantalla. No se usa el nombre: el owner los ordena como quiere.
    sort: Mapped[int] = mapped_column(Integer, default=0)
    #: Un contrato que terminó se APAGA, no se borra: su historia sigue
    #: explicando los meses que ya se facturaron. Apagado no suma al P&L.
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    jan: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    feb: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    mar: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    apr: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    may: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    jun: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    jul: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    aug: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    sep: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    oct: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    nov: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    dec: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))

    def meses(self) -> list[Decimal]:
        return [self.get_month(m) for m in range(1, 13)]

    # Las hermanas con doce columnas —OpexEntry, CostEntry— se leen así, y hay
    # una prueba que lo exige: un bucle que recorra varias no debería necesitar
    # un caso especial por tabla.
    def get_month(self, month: int) -> Decimal:
        return getattr(self, MESES[month - 1]) or Decimal("0")

    def set_month(self, month: int, value: Decimal) -> None:
        setattr(self, MESES[month - 1], value)

    def __repr__(self) -> str:
        return f"<RentLine {self.name}>"
