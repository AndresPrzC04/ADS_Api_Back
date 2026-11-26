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
# 3. ESQUEMAS DE ESTIMACIÓN (CABECERA, DETALLES, SUBSANACIÓN Y CARÁTULA) (RF-SUPT-03, RF-SUPT-07)
# =====================================================================
class EstimacionDetalleCreate(SQLModel):
    id_obra_concepto: int
    cantidad_estimada: Decimal = Field(gt=0)


class EstimacionDetallePublic(SQLModel):
    id_estimacion_detalle: int
    id_estimacion: int
    id_obra_concepto: int
    cantidad_estimada: Decimal


class EstimacionCreate(SQLModel):
    id_obra: int
    id_tipo_estimacion: int
    numero_estimacion: int = Field(gt=0)
    periodo_inicio: date
    periodo_fin: date
    monto_bruto: Optional[Decimal] = Field(default=None, gt=0)
    monto_amortizacion: Decimal = Field(default=Decimal("0.00"), ge=0)
    retencion_atraso: Decimal = Field(default=Decimal("0.00"), ge=0)
    detalles: List[EstimacionDetalleCreate] = Field(default_factory=list)


class EstimacionUpdate(SQLModel):
    """Permite subsanar montos y detalles cuando la estimación está en BORRADOR o RECHAZADA (RF-SUPT-07)."""
    monto_bruto: Optional[Decimal] = Field(default=None, gt=0)
    monto_amortizacion: Optional[Decimal] = Field(default=None, ge=0)
    retencion_atraso: Optional[Decimal] = Field(default=None, ge=0)
    detalles: Optional[List[EstimacionDetalleCreate]] = None


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
    iva: Decimal = Decimal("0.00")
    retencion_atraso: Decimal = Decimal("0.00")
    retencion_sfp: Decimal = Decimal("0.00")
    monto_neto: Decimal


class EstimacionPublicDetalle(EstimacionPublic):
    detalles: List[EstimacionDetallePublic] = Field(default_factory=list)
    revisiones: List[RevisionEstimacionPublic] = Field(default_factory=list)
    facturacion: Optional[FacturacionEstimacionPublic] = None
    pago: Optional[EstimacionPagadaPublic] = None


class EstimacionCaratulaDetallePublic(SQLModel):
    id_obra_concepto: int
    clave_concepto: str
    descripcion: str
    unidad: str
    acumulado_anterior: Decimal
    cantidad_estimada: Decimal
    acumulado_actual: Decimal
    saldo: Decimal
    precio_unitario: Decimal
    importe: Decimal


class EstimacionCaratulaPublic(SQLModel):
    # Datos del contrato y contratista
    numero_contrato: Optional[str] = None
    razon_social_contratista: Optional[str] = None
    rfc_contratista: Optional[str] = None
    numero_fianza_anticipo: Optional[str] = None
    monto_contrato: Decimal
    monto_anticipo: Decimal
    # Totales de la estimación
    fecha_presentacion: date
    numero_estimacion: int
    tipo_estimacion: str
    importe_estimado: Decimal
    acumulado_anterior: Decimal
    acumulado_actual: Decimal
    saldo_por_estimar: Decimal
    amortizacion_actual: Decimal
    amortizacion_acumulada_anterior: Decimal
    amortizacion_acumulada_actual: Decimal
    saldo_por_amortizar: Decimal
    iva: Decimal
    retencion_atraso: Decimal
    retencion_sfp: Decimal
    total_neto: Decimal
    # Desglose por concepto
    detalles: List[EstimacionCaratulaDetallePublic] = Field(default_factory=list)
