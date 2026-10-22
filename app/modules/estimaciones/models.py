from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import String, Integer, Boolean, Date, DateTime, Numeric, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class TipoEstimacion(Base):
    __tablename__ = "tipo_estimacion"

    id_tipo_estimacion: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)  # Ordinaria, Adicional, Extraordinaria
    descripcion: Mapped[Optional[str]] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    estimaciones: Mapped[List["Estimacion"]] = relationship(back_populates="tipo_estimacion")


class Estimacion(Base):
    __tablename__ = "estimaciones"

    id_estimacion: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_obra: Mapped[int] = mapped_column(ForeignKey("obras.id_obra"), nullable=False)
    id_contrato: Mapped[Optional[int]] = mapped_column(ForeignKey("contratos.id_contrato"), nullable=True)
    id_superintendente: Mapped[int] = mapped_column(ForeignKey("superintendente.id_superintendente"), nullable=False)
    id_tipo_estimacion: Mapped[int] = mapped_column(ForeignKey("tipo_estimacion.id_tipo_estimacion"), nullable=False)
    
    numero_estimacion: Mapped[int] = mapped_column(Integer, nullable=False)
    periodo_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    periodo_fin: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_presentacion: Mapped[date] = mapped_column(Date, default=func.current_date())
    
    monto_bruto: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0.00"))
    monto_amortizacion: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0.00"))
    monto_neto: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0.00"))
    
    # Estados: BORRADOR, EN_REVISION, APROBADA, RECHAZADA, AUTORIZADA_PAGO
    estado: Mapped[str] = mapped_column(String(50), default="BORRADOR")

    # Relaciones internas del módulo
    tipo_estimacion: Mapped["TipoEstimacion"] = relationship(back_populates="estimaciones")
    facturacion: Mapped[Optional["FacturacionEstimacion"]] = relationship(
        back_populates="estimacion", uselist=False, cascade="all, delete-orphan"
    )
    revisiones: Mapped[List["RevisionEstimacion"]] = relationship(
        back_populates="estimacion", cascade="all, delete-orphan"
    )
    generadores: Mapped[List["Generador"]] = relationship(
        back_populates="estimacion", cascade="all, delete-orphan"
    )


class FacturacionEstimacion(Base):
    __tablename__ = "facturacion_estimacion"

    id_factura: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_estimacion: Mapped[int] = mapped_column(
        ForeignKey("estimaciones.id_estimacion"), unique=True, nullable=False
    )
    folio_fiscal: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    ruta_pdf: Mapped[str] = mapped_column(String(500), nullable=False)
    ruta_xml: Mapped[str] = mapped_column(String(500), nullable=False)
    monto_factura: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    fecha_carga: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    estimacion: Mapped["Estimacion"] = relationship(back_populates="facturacion")


class RevisionEstimacion(Base):
    __tablename__ = "revision_estimaciones"

    id_revision: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_estimacion: Mapped[int] = mapped_column(ForeignKey("estimaciones.id_estimacion"), nullable=False)
    id_supervisor: Mapped[int] = mapped_column(ForeignKey("supervisor.id_supervisor"), nullable=False)
    fecha_recepcion: Mapped[date] = mapped_column(Date, default=func.current_date(), nullable=False)
    fecha_autorizacion: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    estatus_revision: Mapped[str] = mapped_column(String(50), default="PENDIENTE")  # PENDIENTE, APROBADA, RECHAZADA
    monto_autorizado_neto: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0.00"))

    estimacion: Mapped["Estimacion"] = relationship(back_populates="revisiones")


class Generador(Base):
    __tablename__ = "generadores"

    id_generador: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_estimacion: Mapped[int] = mapped_column(ForeignKey("estimaciones.id_estimacion"), nullable=False)
    id_concepto: Mapped[int] = mapped_column(ForeignKey("conceptos_catalogo.id_concepto"), nullable=False)
    ubicacion_tramo: Mapped[str] = mapped_column(String(250), nullable=False)
    cant_ejecutada: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    croquis_url: Mapped[Optional[str]] = mapped_column(String(500))
    observaciones: Mapped[Optional[str]] = mapped_column(Text)

    estimacion: Mapped["Estimacion"] = relationship(back_populates="generadores")
    validaciones: Mapped[List["GeneradorValidacion"]] = relationship(
        back_populates="generador", cascade="all, delete-orphan"
    )


class GeneradorValidacion(Base):
    __tablename__ = "generadores_validacion"

    id_validacion_gen: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_generador: Mapped[int] = mapped_column(ForeignKey("generadores.id_generador"), nullable=False)
    cant_aprobada: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    observaciones_auditoria: Mapped[Optional[str]] = mapped_column(Text)

    generador: Mapped["Generador"] = relationship(back_populates="validaciones")