from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional
from sqlmodel import Field, SQLModel


# =====================================================================
# 1. ESQUEMAS DE REVISIÓN TÉCNICA Y PLAZOS DE 15 DÍAS (RF-SUP-02, RF-SUP-06)
# =====================================================================
class DictamenRevisionInput(SQLModel):
    estatus_dictamen: Literal["APROBADA", "RECHAZADA"]
    firma_electronica_supervisor: str = Field(min_length=6)
    monto_autorizado_neto: Optional[Decimal] = Field(default=None, ge=0)
    observaciones_rechazo: Optional[str] = None


class RevisionEstimacionPublic(SQLModel):
    id_revision: int
    id_estimacion: int
    id_supervisor: int
    id_estatus_revision: int
    clave_estatus_revision: Optional[str] = None
    version_revisada: int
    fecha_recepcion: date
    fecha_autorizacion: Optional[date] = None
    observaciones_rechazo: Optional[str] = None
    monto_autorizado_neto: Decimal
    sello_firma_supervisor: Optional[str] = None
    advertencia_calidad: Optional[str] = None


class AlertaPlazoRevisionPublic(SQLModel):
    id_revision: int
    id_estimacion: int
    id_obra: int
    numero_estimacion: int
    version_revisada: int
    fecha_recepcion: date
    dias_transcurridos: int
    dias_restantes_plazo_15: int
    nivel_alerta: str
    mensaje: str


# =====================================================================
# 2. ESQUEMAS DE FACTURACIÓN CFDI Y PAGO LIQUIDADO (RF-SUPT-06, RF-RES-03)
# =====================================================================
class AutorizacionPagoInput(SQLModel):
    firma_electronica_residente: str = Field(min_length=6)


class FacturacionEstimacionCreate(SQLModel):
    id_estimacion: int
    folio_fiscal: str = Field(max_length=100)
    monto_factura: Decimal = Field(gt=0)
    ruta_pdf: str = Field(max_length=255)
    ruta_xml: str = Field(max_length=255)


class FacturacionEstimacionPublic(SQLModel):
    id_factura: int
    id_estimacion: int
    folio_fiscal: str
    monto_factura: Decimal
    ruta_pdf: str
    ruta_xml: str
    fecha_carga: datetime


class EstimacionPagadaCreate(SQLModel):
    id_estimacion: int
    folio_estimacion: str = Field(max_length=100)
    monto_pagado: Decimal = Field(gt=0)
    fecha_pago: date = Field(default_factory=date.today)


class EstimacionPagadaPublic(SQLModel):
    id_estimacion: int
    id_estatus_pago: int
    folio_estimacion: str
    monto_pagado: Decimal
    fecha_pago: date


# =====================================================================
# 3. ESQUEMAS DE ESTIMACIÓN (CABECERA, SUBSANACIÓN Y DETALLE) (RF-SUPT-03, RF-SUPT-07)
# =====================================================================
class EstimacionCreate(SQLModel):
    id_obra: int
    id_tipo_estimacion: int
    numero_estimacion: int = Field(gt=0)
    periodo_inicio: date
    periodo_fin: date
    monto_bruto: Decimal = Field(gt=0)
    monto_amortizacion: Decimal = Field(default=Decimal("0.00"), ge=0)


class EstimacionUpdate(SQLModel):
    """Permite subsanar montos cuando la estimación está en BORRADOR o RECHAZADA (RF-SUPT-07)."""
    monto_bruto: Optional[Decimal] = Field(default=None, gt=0)
    monto_amortizacion: Optional[Decimal] = Field(default=None, ge=0)


class EstimacionPublic(SQLModel):
    id_estimacion: int
    id_obra: int
    id_superintendente: int
    id_tipo_estimacion: int
    clave_tipo_estimacion: Optional[str] = None
    id_estatus: int
    clave_estatus: Optional[str] = None
    numero_estimacion: int
    version_subsanacion: int
    periodo_inicio: date
    periodo_fin: date
    fecha_presentacion: date
    monto_bruto: Decimal
    monto_amortizacion: Decimal
    monto_neto: Decimal


class EstimacionPublicDetalle(EstimacionPublic):
    revisiones: List[RevisionEstimacionPublic] = []
    facturacion: Optional[FacturacionEstimacionPublic] = None
    pago: Optional[EstimacionPagadaPublic] = None
