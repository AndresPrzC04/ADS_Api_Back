from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


# ==========================================
# 1. TIPO DE ESTIMACIÓN (Catálogo)
# ==========================================
class TipoEstimacionBase(BaseModel):
    nombre: str = Field(..., max_length=100, examples=["Ordinaria", "Adicional", "Extraordinaria"])
    descripcion: Optional[str] = None


class TipoEstimacionCreate(TipoEstimacionBase):
    pass


class TipoEstimacionUpdate(BaseModel):
    nombre: Optional[str] = Field(None, max_length=100)
    descripcion: Optional[str] = None
    activo: Optional[bool] = None


class TipoEstimacionPublic(TipoEstimacionBase):
    id_tipo_estimacion: int
    activo: bool

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 2. GENERADOR VALIDACIÓN (Auditoría técnica)
# ==========================================
class GeneradorValidacionBase(BaseModel):
    id_generador: int
    cant_aprobada: Decimal = Field(..., ge=0)
    observaciones_auditoria: Optional[str] = None


class GeneradorValidacionCreate(GeneradorValidacionBase):
    pass


class GeneradorValidacionUpdate(BaseModel):
    cant_aprobada: Optional[Decimal] = Field(None, ge=0)
    observaciones_auditoria: Optional[str] = None


class GeneradorValidacionPublic(GeneradorValidacionBase):
    id_validacion_gen: int

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 3. GENERADOR DE OBRA
# ==========================================
class GeneradorBase(BaseModel):
    id_estimacion: int
    id_concepto: int
    ubicacion_tramo: str = Field(..., max_length=250)
    cant_ejecutada: Decimal = Field(..., gt=0)
    croquis_url: Optional[str] = Field(None, max_length=500)
    observaciones: Optional[str] = None


class GeneradorCreate(GeneradorBase):
    pass


class GeneradorUpdate(BaseModel):
    ubicacion_tramo: Optional[str] = Field(None, max_length=250)
    cant_ejecutada: Optional[Decimal] = Field(None, gt=0)
    croquis_url: Optional[str] = Field(None, max_length=500)
    observaciones: Optional[str] = None


class GeneradorPublic(GeneradorBase):
    id_generador: int
    validaciones: List[GeneradorValidacionPublic] = []

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 4. REVISIÓN DE ESTIMACIÓN (Supervisor)
# ==========================================
class RevisionEstimacionBase(BaseModel):
    id_estimacion: int
    id_supervisor: int
    fecha_recepcion: date
    estatus_revision: str = Field(default="PENDIENTE", examples=["PENDIENTE", "APROBADA", "RECHAZADA"])
    monto_autorizado_neto: Decimal = Field(default=Decimal("0.00"), ge=0)


class RevisionEstimacionCreate(RevisionEstimacionBase):
    pass


class RevisionEstimacionUpdate(BaseModel):
    fecha_autorizacion: Optional[date] = None
    estatus_revision: Optional[str] = None
    monto_autorizado_neto: Optional[Decimal] = Field(None, ge=0)


class RevisionEstimacionPublic(RevisionEstimacionBase):
    id_revision: int
    fecha_autorizacion: Optional[date] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 5. FACTURACIÓN DE ESTIMACIÓN (CFDI)
# ==========================================
class FacturacionEstimacionBase(BaseModel):
    id_estimacion: int
    folio_fiscal: str = Field(..., max_length=100, description="UUID del CFDI")
    ruta_pdf: str = Field(..., max_length=500)
    ruta_xml: str = Field(..., max_length=500)
    monto_factura: Decimal = Field(..., gt=0)


class FacturacionEstimacionCreate(FacturacionEstimacionBase):
    pass


class FacturacionEstimacionUpdate(BaseModel):
    folio_fiscal: Optional[str] = Field(None, max_length=100)
    ruta_pdf: Optional[str] = Field(None, max_length=500)
    ruta_xml: Optional[str] = Field(None, max_length=500)
    monto_factura: Optional[Decimal] = Field(None, gt=0)


class FacturacionEstimacionPublic(FacturacionEstimacionBase):
    id_factura: int
    fecha_carga: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 6. ESTIMACIÓN (Cabecera)
# ==========================================
class EstimacionBase(BaseModel):
    id_obra: int
    id_contrato: Optional[int] = None
    id_superintendente: int
    id_tipo_estimacion: int
    numero_estimacion: int = Field(..., gt=0)
    periodo_inicio: date
    periodo_fin: date
    monto_amortizacion: Decimal = Field(default=Decimal("0.00"), ge=0)


class EstimacionCreate(EstimacionBase):
    pass


class EstimacionUpdate(BaseModel):
    periodo_inicio: Optional[date] = None
    periodo_fin: Optional[date] = None
    monto_amortizacion: Optional[Decimal] = Field(None, ge=0)
    estado: Optional[str] = None


class EstimacionPublic(EstimacionBase):
    id_estimacion: int
    fecha_presentacion: date
    monto_bruto: Decimal
    monto_neto: Decimal
    estado: str
    generadores: List[GeneradorPublic] = []
    revisiones: List[RevisionEstimacionPublic] = []
    facturacion: Optional[FacturacionEstimacionPublic] = None

    model_config = ConfigDict(from_attributes=True)