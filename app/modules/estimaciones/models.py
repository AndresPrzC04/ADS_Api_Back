from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import Column, Numeric, Text
from sqlmodel import SQLModel, Field, Relationship


# =====================================================================
# 1. TIPO DE ESTIMACIÓN (Catálogo)
# =====================================================================
class TipoEstimacionBase(SQLModel):
    nombre: str = Field(unique=True, index=True, max_length=100)
    descripcion: Optional[str] = Field(default=None, sa_column=Column(Text))


class TipoEstimacion(TipoEstimacionBase, table=True):
    __tablename__ = "tipo_estimacion"

    id_tipo_estimacion: Optional[int] = Field(default=None, primary_key=True)
    activo: bool = Field(default=True)

    estimaciones: List["Estimacion"] = Relationship(back_populates="tipo_estimacion")


class TipoEstimacionCreate(TipoEstimacionBase):
    pass


class TipoEstimacionUpdate(SQLModel):
    nombre: Optional[str] = Field(default=None, max_length=100)
    descripcion: Optional[str] = None
    activo: Optional[bool] = None


class TipoEstimacionPublic(TipoEstimacionBase):
    id_tipo_estimacion: int
    activo: bool


# =====================================================================
# 2. VALIDACIÓN DE GENERADOR (Auditoría Técnica)
# =====================================================================
class GeneradorValidacionBase(SQLModel):
    id_generador: int = Field(foreign_key="generadores.id_generador")
    cant_aprobada: Decimal = Field(
        default=Decimal("0.0000"), sa_column=Column(Numeric(14, 4), nullable=False)
    )
    observaciones_auditoria: Optional[str] = Field(default=None, sa_column=Column(Text))


class GeneradorValidacion(GeneradorValidacionBase, table=True):
    __tablename__ = "generadores_validacion"

    id_validacion_gen: Optional[int] = Field(default=None, primary_key=True)
    generador: Optional["Generador"] = Relationship(back_populates="validaciones")


class GeneradorValidacionCreate(GeneradorValidacionBase):
    pass


class GeneradorValidacionUpdate(SQLModel):
    cant_aprobada: Optional[Decimal] = None
    observaciones_auditoria: Optional[str] = None


class GeneradorValidacionPublic(GeneradorValidacionBase):
    id_validacion_gen: int


# =====================================================================
# 3. NÚMERO GENERADOR DE OBRA
# =====================================================================
class GeneradorBase(SQLModel):
    id_estimacion: int = Field(foreign_key="estimaciones.id_estimacion")
    id_concepto: int = Field(foreign_key="conceptos_catalogo.id_concepto")
    ubicacion_tramo: str = Field(max_length=250)
    cant_ejecutada: Decimal = Field(
        default=Decimal("0.0000"), sa_column=Column(Numeric(14, 4), nullable=False)
    )
    croquis_url: Optional[str] = Field(default=None, max_length=500)
    observaciones: Optional[str] = Field(default=None, sa_column=Column(Text))


class Generador(GeneradorBase, table=True):
    __tablename__ = "generadores"

    id_generador: Optional[int] = Field(default=None, primary_key=True)

    estimacion: Optional["Estimacion"] = Relationship(back_populates="generadores")
    validaciones: List[GeneradorValidacion] = Relationship(back_populates="generador")


class GeneradorCreate(GeneradorBase):
    pass


class GeneradorUpdate(SQLModel):
    ubicacion_tramo: Optional[str] = Field(default=None, max_length=250)
    cant_ejecutada: Optional[Decimal] = None
    croquis_url: Optional[str] = Field(default=None, max_length=500)
    observaciones: Optional[str] = None


class GeneradorPublic(GeneradorBase):
    id_generador: int


# =====================================================================
# 4. REVISIÓN DE ESTIMACIÓN (Supervisor)
# =====================================================================
class RevisionEstimacionBase(SQLModel):
    id_estimacion: int = Field(foreign_key="estimaciones.id_estimacion")
    id_supervisor: int = Field(foreign_key="supervisor.id_supervisor")
    fecha_recepcion: date = Field(default_factory=date.today)
    estatus_revision: str = Field(default="PENDIENTE", max_length=50)
    monto_autorizado_neto: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(16, 2), nullable=False)
    )


class RevisionEstimacion(RevisionEstimacionBase, table=True):
    __tablename__ = "revision_estimaciones"

    id_revision: Optional[int] = Field(default=None, primary_key=True)
    fecha_autorizacion: Optional[date] = Field(default=None)

    estimacion: Optional["Estimacion"] = Relationship(back_populates="revisiones")


class RevisionEstimacionCreate(RevisionEstimacionBase):
    pass


class RevisionEstimacionUpdate(SQLModel):
    fecha_autorizacion: Optional[date] = None
    estatus_revision: Optional[str] = None
    monto_autorizado_neto: Optional[Decimal] = None


class RevisionEstimacionPublic(RevisionEstimacionBase):
    id_revision: int
    fecha_autorizacion: Optional[date] = None


# =====================================================================
# 5. FACTURACIÓN DE ESTIMACIÓN (CFDI)
# =====================================================================
class FacturacionEstimacionBase(SQLModel):
    id_estimacion: int = Field(foreign_key="estimaciones.id_estimacion", unique=True)
    folio_fiscal: str = Field(unique=True, index=True, max_length=100)
    ruta_pdf: str = Field(max_length=500)
    ruta_xml: str = Field(max_length=500)
    monto_factura: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(16, 2), nullable=False)
    )


class FacturacionEstimacion(FacturacionEstimacionBase, table=True):
    __tablename__ = "facturacion_estimacion"

    id_factura: Optional[int] = Field(default=None, primary_key=True)
    fecha_carga: datetime = Field(default_factory=datetime.utcnow)

    estimacion: Optional["Estimacion"] = Relationship(back_populates="facturacion")


class FacturacionEstimacionCreate(FacturacionEstimacionBase):
    pass


class FacturacionEstimacionUpdate(SQLModel):
    folio_fiscal: Optional[str] = Field(default=None, max_length=100)
    ruta_pdf: Optional[str] = Field(default=None, max_length=500)
    ruta_xml: Optional[str] = Field(default=None, max_length=500)
    monto_factura: Optional[Decimal] = None


class FacturacionEstimacionPublic(FacturacionEstimacionBase):
    id_factura: int
    fecha_carga: datetime


# =====================================================================
# 6. ESTIMACIÓN (Cabecera)
# =====================================================================
class EstimacionBase(SQLModel):
    id_obra: int = Field(foreign_key="obras.id_obra")
    id_contrato: Optional[int] = Field(default=None, foreign_key="contratos.id_contrato")
    id_superintendente: int = Field(foreign_key="superintendente.id_superintendente")
    id_tipo_estimacion: int = Field(foreign_key="tipo_estimacion.id_tipo_estimacion")
    numero_estimacion: int = Field(index=True)
    periodo_inicio: date
    periodo_fin: date
    monto_amortizacion: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(16, 2), nullable=False)
    )


class Estimacion(EstimacionBase, table=True):
    __tablename__ = "estimaciones"

    id_estimacion: Optional[int] = Field(default=None, primary_key=True)
    fecha_presentacion: date = Field(default_factory=date.today)
    monto_bruto: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(16, 2), nullable=False)
    )
    monto_neto: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(16, 2), nullable=False)
    )
    estado: str = Field(default="BORRADOR", max_length=50)

    tipo_estimacion: Optional[TipoEstimacion] = Relationship(back_populates="estimaciones")
    facturacion: Optional[FacturacionEstimacion] = Relationship(back_populates="estimacion")
    revisiones: List[RevisionEstimacion] = Relationship(back_populates="estimacion")
    generadores: List[Generador] = Relationship(back_populates="estimacion")


class EstimacionCreate(EstimacionBase):
    pass


class EstimacionUpdate(SQLModel):
    periodo_inicio: Optional[date] = None
    periodo_fin: Optional[date] = None
    monto_amortizacion: Optional[Decimal] = None
    estado: Optional[str] = None


class EstimacionPublic(EstimacionBase):
    id_estimacion: int
    fecha_presentacion: date
    monto_bruto: Decimal
    monto_neto: Decimal
    estado: str


class EstimacionPublicDetalle(EstimacionPublic):
    generadores: List[GeneradorPublic] = []
    revisiones: List[RevisionEstimacionPublic] = []
    facturacion: Optional[FacturacionEstimacionPublic] = None