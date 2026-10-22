from datetime import date, datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, ConfigDict, Field


# ==========================================
# 1. ARCHIVO ADJUNTO (Tabla Polimórfica)
# ==========================================
class ArchivoAdjuntoBase(BaseModel):
    entidad_tipo: Literal["BITACORA", "GENERADOR", "CALIDAD"]
    entidad_id: int
    ruta_archivo: str = Field(..., max_length=500)
    descripcion_pie_foto: Optional[str] = Field(None, max_length=300)


class ArchivoAdjuntoCreate(ArchivoAdjuntoBase):
    pass


class ArchivoAdjuntoUpdate(BaseModel):
    descripcion_pie_foto: Optional[str] = Field(None, max_length=300)


class ArchivoAdjuntoPublic(ArchivoAdjuntoBase):
    id_archivo_adjunto: int
    fecha_carga: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 2. BITÁCORA NOTA (Append-Only / Inmutable)
# ==========================================
class BitacoraNotaBase(BaseModel):
    id_obra: int
    id_usuario: int
    tipo_nota: str = Field(
        ..., max_length=50, examples=["APERTURA", "ORDEN", "SOLICITUD", "SEGUIMIENTO", "CIERRE"]
    )
    asunto: str = Field(..., max_length=250)
    descripcion: str


class BitacoraNotaCreate(BitacoraNotaBase):
    pass


class BitacoraNotaFirma(BaseModel):
    """Única acción posterior permitida sobre una nota creada: su firmado electrónico."""
    sello_digital: str = Field(..., min_length=10, max_length=255)


class BitacoraNotaPublic(BitacoraNotaBase):
    id_nota: int
    consecutivo_nota: int
    fecha_registro: datetime
    firmada: bool
    sello_digital: Optional[str] = None
    archivos_adjuntos: List[ArchivoAdjuntoPublic] = []

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 3. EXPEDIENTE DOCUMENTO (Repositorio)
# ==========================================
class ExpedienteDocumentoBase(BaseModel):
    id_obra: int
    fase: str = Field(..., max_length=100, examples=["01_PRELIMINAR", "02_CONTRATACION", "03_EJECUCION", "04_CIERRE"])
    nombre: str = Field(..., max_length=250)
    version: int = Field(default=1, ge=1)
    archivo_url: str = Field(..., max_length=500)
    hash_sha256: str = Field(..., min_length=64, max_length=64)


class ExpedienteDocumentoCreate(ExpedienteDocumentoBase):
    pass


class ExpedienteDocumentoUpdate(BaseModel):
    estatus: Optional[str] = Field(None, examples=["EN_REVISION", "APROBADO", "RECHAZADO"])
    version: Optional[int] = Field(None, ge=1)
    archivo_url: Optional[str] = Field(None, max_length=500)
    hash_sha256: Optional[str] = Field(None, min_length=64, max_length=64)


class ExpedienteDocumentoPublic(ExpedienteDocumentoBase):
    id_documento: int
    estatus: str
    fecha_subida: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 4. CONTROL DE CALIDAD Y PRUEBAS DE LAB
# ==========================================
class ControlCalidadPruebaBase(BaseModel):
    id_obra: int
    id_concepto: int
    tipo_ensayo: str = Field(..., max_length=150, examples=["Compresión de cilindros de concreto", "Compactación Proctor"])
    fecha_muestreo: date
    resultado_dictamen: str = Field(..., max_length=100, examples=["APROBADO", "RECHAZADO"])
    url_reporte_laboratorio: str = Field(..., max_length=500)


class ControlCalidadPruebaCreate(ControlCalidadPruebaBase):
    pass


class ControlCalidadPruebaUpdate(BaseModel):
    resultado_dictamen: Optional[str] = Field(None, max_length=100)
    url_reporte_laboratorio: Optional[str] = Field(None, max_length=500)


class ControlCalidadPruebaPublic(ControlCalidadPruebaBase):
    id_prueba: int
    archivos_adjuntos: List[ArchivoAdjuntoPublic] = []

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 5. REPORTE DIARIO DE SUPERVISIÓN
# ==========================================
class ReporteDiarioSupervisionBase(BaseModel):
    id_obra: int
    id_supervisor: int
    fecha_reporte: date
    clima: str = Field(..., max_length=100, examples=["Soleado", "Lluvia moderada"])
    estado_fuerza_trabajo: int = Field(..., ge=0, description="Número total de trabajadores en sitio")
    maquinaria_activa: Optional[str] = None
    incidencias_relevantes: Optional[str] = None


class ReporteDiarioSupervisionCreate(ReporteDiarioSupervisionBase):
    pass


class ReporteDiarioSupervisionUpdate(BaseModel):
    clima: Optional[str] = Field(None, max_length=100)
    estado_fuerza_trabajo: Optional[int] = Field(None, ge=0)
    maquinaria_activa: Optional[str] = None
    incidencias_relevantes: Optional[str] = None


class ReporteDiarioSupervisionPublic(ReporteDiarioSupervisionBase):
    id_reporte: int

    model_config = ConfigDict(from_attributes=True)