from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional
from sqlmodel import Field, SQLModel


# =====================================================================
# 1. EVIDENCIA FOTOGRÁFICA ADJUNTA (Vinculada a Bitácora o a Reporte de Supervisión)
# =====================================================================
class EvidenciaAdjuntaCreate(SQLModel):
    id_nota: Optional[int] = None
    id_reporte: Optional[int] = None
    ruta_archivo: str = Field(max_length=255)
    descripcion_pie_foto: Optional[str] = Field(default=None, max_length=255)


class EvidenciaAdjuntaPublic(SQLModel):
    id_evidencia: int
    id_nota: Optional[int] = None
    id_reporte: Optional[int] = None
    ruta_archivo: str
    descripcion_pie_foto: Optional[str] = None
    fecha_carga: datetime


# =====================================================================
# 2. BITÁCORA ELECTRÓNICA DE OBRA INMUTABLE (RF-RES-01, RF-RES-02, RF-SUPT-05, RF-SUP-03)
# =====================================================================
class BitacoraNotaCreate(SQLModel):
    id_obra: int
    clave_tipo_nota: str = Field(max_length=50)
    asunto: str = Field(max_length=255)
    descripcion: str
    id_obra_concepto_adicional: Optional[int] = None
    cantidad_adicional_autorizada: Optional[Decimal] = Field(default=None, gt=0)


class BitacoraNotaFirmaInput(SQLModel):
    firma_electronica: str = Field(min_length=6)


class BitacoraNotaPublic(SQLModel):
    id_nota: int
    id_obra: int
    id_usuario: int
    id_tipo_nota: int
    clave_tipo_nota: Optional[str] = None
    consecutivo_nota: int
    asunto: str
    descripcion: str
    fecha_registro: datetime
    firmada: bool
    sello_digital: Optional[str] = None
    evidencias: List[EvidenciaAdjuntaPublic] = []


# =====================================================================
# 3. CONTROL DE CALIDAD Y PRUEBAS DE LABORATORIO (Tabla 3NF: Control_Calidad_Pruebas)
# =====================================================================
class ControlCalidadPruebaCreate(SQLModel):
    id_obra_concepto: int
    id_tipo_ensayo: int
    clave_dictamen: Literal["APROBADO", "RECHAZADO"]
    fecha_muestreo: date
    valor_obtenido: str = Field(max_length=100)
    url_reporte_laboratorio: str = Field(max_length=255)


class ControlCalidadPruebaPublic(SQLModel):
    id_prueba: int
    id_obra_concepto: int
    id_tipo_ensayo: int
    id_estatus_dictamen: int
    clave_dictamen: Optional[str] = None
    fecha_muestreo: date
    valor_obtenido: str
    url_reporte_laboratorio: str


# =====================================================================
# 4. REPORTE DIARIO DE SUPERVISIÓN E INCIDENTES (RF-SUP-03)
# =====================================================================
class ReporteIncidenteInput(SQLModel):
    suceso: str
    accion_solucion: Optional[str] = None
    clave_estatus: Literal["CREADO", "EMITIDO", "ATENDIDO"] = "CREADO"


class ReporteIncidenteEstatusUpdate(SQLModel):
    clave_estatus: Literal["CREADO", "EMITIDO", "ATENDIDO"]
    accion_solucion: Optional[str] = None


class ReporteIncidentePublic(SQLModel):
    id_incidente: int
    id_reporte: int
    id_estatus_incidente: int
    clave_estatus: str
    suceso: str
    accion_solucion: Optional[str] = None


class ReporteDiarioSupervisionCreate(SQLModel):
    """RN-SUP-03.4: Permite crear en estado BORRADOR con campos parciales / incompletos."""
    id_obra: int
    fecha_reporte: date = Field(default_factory=date.today)
    actividades_realizadas: Optional[str] = None
    clima: Optional[Literal["SOLEADO", "NUBLADO", "LLUVIOSO", "TORMENTA"]] = None
    horas_lluvia: Optional[Decimal] = Field(default=Decimal("0.00"), ge=0, le=24)
    maquinaria_cantidad: Optional[int] = Field(default=0, ge=0)
    equipo_cantidad: Optional[int] = Field(default=0, ge=0)
    personal_cantidad: Optional[int] = Field(default=0, ge=0)
    porcentaje_avance_reportado: Optional[Decimal] = Field(default=None, ge=0, le=100)
    incidentes: List[ReporteIncidenteInput] = Field(default_factory=list)


class ReporteDiarioSupervisionUpdate(SQLModel):
    """RN-SUP-03.4: Editable mientras se encuentre en BORRADOR o ENVIADO sin firma."""
    actividades_realizadas: Optional[str] = None
    clima: Optional[Literal["SOLEADO", "NUBLADO", "LLUVIOSO", "TORMENTA"]] = None
    horas_lluvia: Optional[Decimal] = Field(default=None, ge=0, le=24)
    maquinaria_cantidad: Optional[int] = Field(default=None, ge=0)
    equipo_cantidad: Optional[int] = Field(default=None, ge=0)
    personal_cantidad: Optional[int] = Field(default=None, ge=0)
    porcentaje_avance_reportado: Optional[Decimal] = Field(default=None, ge=0, le=100)
    incidentes: Optional[List[ReporteIncidenteInput]] = None


class ReporteDiarioFirmaInput(SQLModel):
    firma_electronica_supervisor: str = Field(min_length=6)


class ReporteDiarioSupervisionPublic(SQLModel):
    id_reporte: int
    id_obra: int
    id_supervisor: int
    fecha_reporte: date
    id_estatus_reporte: int
    estatus_reporte: str
    actividades_realizadas: Optional[str] = None
    clima: Optional[str] = None
    horas_lluvia: Decimal
    maquinaria_cantidad: int
    equipo_cantidad: int
    personal_cantidad: int
    porcentaje_avance_reportado: Optional[Decimal] = None
    porcentaje_financiero_actual: Decimal = Decimal("0.00")
    firmado: bool
    sello_digital: Optional[str] = None
    fecha_envio: Optional[datetime] = None
    fecha_firma: Optional[datetime] = None
    incidentes: List[ReporteIncidentePublic] = Field(default_factory=list)
    evidencias: List[EvidenciaAdjuntaPublic] = Field(default_factory=list)
    advertencia_calidad: Optional[str] = None
