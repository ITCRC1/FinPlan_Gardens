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
        # Dos contratos con el MISMO nombre en el mismo escenario son un error
        # de digitación, no dos inquilinos: el segundo pisaría al primero en
        # cualquier reporte que agrupe por nombre.
        UniqueConstraint("scenario_id", "name", name="uq_rent_line_nombre"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)

    name: Mapped[str] = mapped_column(String(120))
    #: Dónde está el local. Texto libre: «Sabor», «Lobby», «Área Recreativa».
    ubicacion: Mapped[str] = mapped_column(String(120), default="")
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
