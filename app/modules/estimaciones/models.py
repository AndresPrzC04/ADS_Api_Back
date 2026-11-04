from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Literal
from sqlmodel import Field, SQLModel


# =====================================================================
# 1. ESQUEMAS DE NÚMEROS GENERADORES Y VALIDACIÓN (RF-SUPT-04, RF-SUP-01)
# =====================================================================
class GeneradorCreate(SQLModel):
    id_estimacion: int
    id_concepto: int
    ubicacion_tramo: str = Field(max_length=255)
    cant_ejecutada: Decimal = Field(gt=0)
    croquis_url: Optional[str] = Field(default=None, max_length=255)
    observaciones: Optional[str] = None


class GeneradorUpdate(SQLModel):
    ubicacion_tramo: Optional[str] = Field(default=None, max_length=255)
    cant_ejecutada: Optional[Decimal] = Field(default=None, gt=0)
    croquis_url: Optional[str] = Field(default=None, max_length=255)
    observaciones: Optional[str] = None


class GeneradorValidacionCreate(SQLModel):
    id_generador: int
    cant_aprobada: Decimal = Field(ge=0)
    observaciones_auditoria: Optional[str] = None


class GeneradorValidacionPublic(SQLModel):
    id_validacion_gen: int
    id_generador: int
    version_revisada: int
    cant_aprobada: Decimal
    observaciones_auditoria: Optional[str] = None
    fecha_validacion: datetime
    advertencia_calidad: Optional[str] = None


class GeneradorPublic(SQLModel):
    id_generador: int
    id_estimacion: int
    id_concepto: int
    ubicacion_tramo: str
    cant_ejecutada: Decimal
    croquis_url: Optional[str] = None
    observaciones: Optional[str] = None
    tiene_ensayo_rechazado: bool = False


# =====================================================================
# 2. ESQUEMAS DE REVISIÓN TÉCNICA Y PLAZOS DE 15 DÍAS (RF-SUP-02, RF-SUP-05, RF-SUP-06)
# =====================================================================
class DictamenRevisionInput(SQLModel):
    estatus_dictamen: Literal["APROBADA", "RECHAZADA"]
    firma_electronica_supervisor: str = Field(min_length=6)
    observaciones_rechazo: Optional[str] = None
    retencion_economica_atraso: Decimal = Field(default=Decimal("0.00"), ge=0)


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


class AlertaPlazoRevisionPublic(SQLModel):
    id_revision: int
    id_estimacion: int
    id_obra: int
    numero_estimacion: int
    version_revisada: int
    fecha_recepcion: date
    dias_transcurridos: int
    dias_restantes_plazo_15: int
    nivel_alerta: str  # 'EN_PLAZO (VERDE)', 'PREVENTIVA (AMARILLA)', 'CRITICA_VENCIDA (ROJA)'
    mensaje: str


# =====================================================================
# 3. ESQUEMAS DE FACTURACIÓN CFDI Y PAGO LIQUIDADO (RF-SUPT-06, RF-RES-03, RF-RES-05)
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
# 4. ESQUEMAS DE ESTIMACIÓN (CABECERA Y DETALLE) (RF-SUPT-03, RF-SUPT-07)
# =====================================================================
class EstimacionCreate(SQLModel):
    id_obra: int
    id_tipo_estimacion: int
    numero_estimacion: int = Field(gt=0)
    periodo_inicio: date
    periodo_fin: date
    monto_amortizacion: Decimal = Field(default=Decimal("0.00"), ge=0)


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
    generadores: List[GeneradorPublic] = []
    revisiones: List[RevisionEstimacionPublic] = []
    facturacion: Optional[FacturacionEstimacionPublic] = None
    pago: Optional[EstimacionPagadaPublic] = None
