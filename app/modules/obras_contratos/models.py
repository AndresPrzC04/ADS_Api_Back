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
    monto_anticipo: Decimal = Field(default=Decimal("0.00"), ge=0)
    archivo_contrato: Optional[str] = Field(default=None, max_length=255)


class ContratoUpdate(SQLModel):
    id_contratista: Optional[int] = None
    numero_contrato: Optional[str] = Field(default=None, max_length=100)
    monto_contrato: Optional[Decimal] = Field(default=None, gt=0)
    monto_anticipo: Optional[Decimal] = Field(default=None, ge=0)
    archivo_contrato: Optional[str] = Field(default=None, max_length=255)


class ContratoPublic(SQLModel):
    id_contrato: int
    id_obra: int
    id_contratista: int
    id_estatus: int
    numero_contrato: str
    monto_contrato: Decimal
    monto_anticipo: Decimal = Decimal("0.00")
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
# 4. CATÁLOGO MAESTRO GENERAL Y CONCEPTOS POR OBRA (RF-SUPT-01, RF-RES-04)
# =====================================================================
class ConceptoMaestroCreate(SQLModel):
    id_unidad: int
    partida: str = Field(default="GENERAL", max_length=120)
    subpartida: str = Field(default="GENERAL", max_length=120)
    clave_concepto: str = Field(max_length=100)
    descripcion: str
    precio_referencia: Optional[Decimal] = Field(default=None, gt=0)


class ConceptoMaestroPublic(SQLModel):
    id_concepto_maestro: int
    id_subpartida: int
    partida: str
    subpartida: str
    id_unidad: int
    unidad: str
    clave_concepto: str
    descripcion: str
    precio_referencia: Optional[Decimal] = None
    activo: bool


class ConceptoCatalogoCreate(SQLModel):
    id_obra: Optional[int] = None
    id_concepto_maestro: Optional[int] = None
    id_unidad: Optional[int] = None
    partida: str = Field(default="GENERAL", max_length=120)
    subpartida: str = Field(default="GENERAL", max_length=120)
    clave_concepto: Optional[str] = Field(default=None, max_length=100)
    descripcion: Optional[str] = None
    cantidad_presupuestada: Decimal = Field(ge=0)
    precio_unitario: Decimal = Field(gt=0)


class ConceptoCatalogoUpdate(SQLModel):
    id_unidad: Optional[int] = None
    partida: Optional[str] = Field(default=None, max_length=120)
    subpartida: Optional[str] = Field(default=None, max_length=120)
    clave_concepto: Optional[str] = Field(default=None, max_length=100)
    descripcion: Optional[str] = None
    cantidad_presupuestada: Optional[Decimal] = Field(default=None, ge=0)
    precio_unitario: Optional[Decimal] = Field(default=None, gt=0)


class ConceptoExtraordinarioInyeccion(SQLModel):
    """RF-RES-04: Inyección de concepto extraordinario con dictamen APU y firma electrónica del Residente."""
    id_obra: int
    id_unidad: int
    partida: str = Field(default="EXTRAORDINARIOS", max_length=120)
    subpartida: str = Field(default="EXTRAORDINARIOS", max_length=120)
    clave_concepto: str = Field(max_length=100)
    descripcion: str
    cantidad_presupuestada: Decimal = Field(gt=0)
    precio_unitario: Decimal = Field(gt=0)
    dictamen_apu_url: str = Field(max_length=255)
    firma_electronica_residente: str = Field(min_length=6)


class ConceptoCatalogoPublic(SQLModel):
    id_obra_concepto: int
    id_concepto_maestro: int
    id_obra: int
    id_tipo_concepto: int
    id_unidad: int
    id_subpartida: int
    partida: str
    subpartida: str
    clave_concepto: str
    descripcion: str
    precio_referencia: Optional[Decimal] = None
    cantidad_presupuestada: Decimal
    cantidad_adicional_autorizada: Decimal
    precio_unitario: Decimal
    dictamen_apu_url: Optional[str] = None
    autorizado_por_residente: bool


class ImportacionExcelObraPublic(SQLModel):
    reutilizados_maestro: int
    nuevos_en_maestro: int
    vinculados_a_obra: int
    conceptos: List[ConceptoCatalogoPublic] = Field(default_factory=list)


class SubtotalSubpartidaPublic(SQLModel):
    subpartida: str
    cantidad_conceptos: int
    importe_subtotal: Decimal


class SubtotalPartidaPublic(SQLModel):
    partida: str
    cantidad_conceptos: int
    importe_subtotal: Decimal
    subpartidas: List[SubtotalSubpartidaPublic] = []


class ResumenPresupuestoObraPublic(SQLModel):
    id_obra: int
    nombre_obra: str
    total_conceptos: int
    total_presupuesto_calculado: Decimal
    presupuesto_tope_obra: Decimal
    saldo_disponible_catalogo: Decimal
    partidas: List[SubtotalPartidaPublic] = []


# =====================================================================
# 5. TABLERO DIRECTIVO, CORTES DE AVANCE, REPORTES Y FINIQUITO
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
