from datetime import date
from decimal import Decimal
from typing import List, Optional
from sqlmodel import Field, SQLModel


# =====================================================================
# 1. EMPRESA CONTRATISTA (Tabla: Contratistas en 3NF)
# =====================================================================
class ContratistaCreate(SQLModel):
    rfc: str = Field(min_length=12, max_length=13)
    razon_social: str = Field(max_length=255)


class ContratistaUpdate(SQLModel):
    razon_social: Optional[str] = Field(default=None, max_length=255)
    activo: Optional[bool] = None


class ContratistaPublic(SQLModel):
    id_contratista: int
    rfc: str
    razon_social: str
    activo: bool


# =====================================================================
# 2. OBRA PÚBLICA (RF-ADM-04)
# =====================================================================
class ObraCreate(SQLModel):
    nombre_obra: str = Field(max_length=255)
    presupuesto_total: Decimal = Field(gt=0)
    fecha_inicio: date
    fecha_fin: date


class ObraUpdate(SQLModel):
    nombre_obra: Optional[str] = Field(default=None, max_length=255)
    presupuesto_total: Optional[Decimal] = Field(default=None, gt=0)
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None


class ObraPublic(SQLModel):
    id_obra: int
    id_estatus: int
    clave_estatus: Optional[str] = None
    nombre_obra: str
    presupuesto_total: Decimal
    fecha_inicio: date
    fecha_fin: date


# =====================================================================
# 3. CONTRATO LEGAL Y PÓLIZAS DE FIANZA (RF-ADM-04)
# =====================================================================
class ContratoCreate(SQLModel):
    id_obra: int
    id_contratista: int
    numero_contrato: str = Field(max_length=100)
    monto_contrato: Decimal = Field(gt=0)
    archivo_contrato: Optional[str] = Field(default=None, max_length=255)


class ContratoUpdate(SQLModel):
    id_contratista: Optional[int] = None
    numero_contrato: Optional[str] = Field(default=None, max_length=100)
    monto_contrato: Optional[Decimal] = Field(default=None, gt=0)
    archivo_contrato: Optional[str] = Field(default=None, max_length=255)


class ContratoPublic(SQLModel):
    id_contrato: int
    id_obra: int
    id_contratista: int
    id_estatus: int
    numero_contrato: str
    monto_contrato: Decimal
    archivo_contrato: Optional[str] = None


class PolizaCreate(SQLModel):
    id_contrato: int
    id_tipo_poliza: int
    numero_poliza: str = Field(max_length=100)
    fecha_vencimiento: date
    archivo_poliza: str = Field(max_length=255)


class PolizaUpdate(SQLModel):
    fecha_vencimiento: Optional[date] = None
    archivo_poliza: Optional[str] = Field(default=None, max_length=255)


class PolizaPublic(SQLModel):
    id_poliza: int
    id_contrato: int
    id_tipo_poliza: int
    numero_poliza: str
    fecha_vencimiento: date
    archivo_poliza: str


# =====================================================================
# 4. CATÁLOGO DE CONCEPTOS Y PRECIOS EXTRAORDINARIOS (RF-SUPT-01, RF-RES-04)
# =====================================================================
class ConceptoCatalogoCreate(SQLModel):
    id_obra: int
    id_unidad: int
    clave_concepto: str = Field(max_length=100)
    descripcion: str
    cantidad_presupuestada: Decimal = Field(ge=0)
    precio_unitario: Decimal = Field(gt=0)


class ConceptoCatalogoUpdate(SQLModel):
    id_unidad: Optional[int] = None
    clave_concepto: Optional[str] = Field(default=None, max_length=100)
    descripcion: Optional[str] = None
    cantidad_presupuestada: Optional[Decimal] = Field(default=None, ge=0)
    precio_unitario: Optional[Decimal] = Field(default=None, gt=0)


class ConceptoExtraordinarioInyeccion(SQLModel):
    """RF-RES-04: Inyección de concepto extraordinario con dictamen APU y firma electrónica del Residente."""
    id_obra: int
    id_unidad: int
    clave_concepto: str = Field(max_length=100)
    descripcion: str
    cantidad_presupuestada: Decimal = Field(gt=0)
    precio_unitario: Decimal = Field(gt=0)
    dictamen_apu_url: str = Field(max_length=255)
    firma_electronica_residente: str = Field(min_length=6)


class ConceptoCatalogoPublic(SQLModel):
    id_concepto: int
    id_obra: int
    id_tipo_concepto: int
    id_unidad: int
    clave_concepto: str
    descripcion: str
    cantidad_presupuestada: Decimal
    cantidad_adicional_autorizada: Decimal
    precio_unitario: Decimal
    dictamen_apu_url: Optional[str] = None
    autorizado_por_residente: bool


# =====================================================================
# 5. TABLERO DIRECTIVO, CORTES DE AVANCE, REPORTES Y FINIQUITO (RF-DIR-01, RF-DIR-04, RF-RES-05)
# (Sin Gantt / Programa_ejecucion derogados)
# =====================================================================
class AvanceFisicoPublic(SQLModel):
    id_avance: int
    id_obra: int
    id_reporte: Optional[int] = None
    fecha_corte: date
    porcentaje_fisico: Decimal
    porcentaje_financiero_real: Decimal


class DashboardObraItem(SQLModel):
    id_obra: int
    nombre_obra: str
    estado_general: str
    presupuesto_total: Decimal
    monto_contrato: Decimal
    fecha_inicio: date
    fecha_fin: date
    avance_fisico_real_pct: Decimal
    avance_financiero_real_pct: Decimal
    cumple_candado_fisico_financiero: bool
    alertas_plazo_revision: List[str] = []


class ReporteGerencialFinanciero(SQLModel):
    id_obra: int
    nombre_obra: str
    numero_contrato: Optional[str] = None
    contratista: Optional[str] = None
    presupuesto_total_contratado: Decimal
    monto_bruto_estimado: Decimal
    amortizacion_anticipo_descontada: Decimal
    monto_neto_autorizado: Decimal
    monto_efectivamente_liquidado: Decimal
    saldo_pendiente_por_ejercer: Decimal
    avance_fisico_real_pct: Decimal
    avance_financiero_real_pct: Decimal
    fecha_generacion: date


class FiniquitoSolicitud(SQLModel):
    firma_electronica_residente: str = Field(min_length=6)
    observaciones_finiquito: Optional[str] = None


class ActaFiniquitoResumen(SQLModel):
    id_obra: int
    nombre_obra: str
    numero_contrato: str
    estado_obra: str
    estado_contrato: str
    monto_original_contratado: Decimal
    monto_ejercido_ordinario: Decimal
    monto_ejercido_adicionales: Decimal
    monto_ejercido_extraordinarios: Decimal
    monto_total_ejercido: Decimal
    total_anticipo_amortizado: Decimal
    saldo_final_liquidado: Decimal
    sello_digital_residente: str
