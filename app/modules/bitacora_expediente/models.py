from datetime import date, datetime
from typing import List, Optional, Literal
from sqlalchemy import Column, Text, and_
from sqlalchemy.orm import foreign
from sqlmodel import SQLModel, Field, Relationship


# =====================================================================
# 1. ARCHIVO ADJUNTO (Tabla Polimórfica)
# =====================================================================
class ArchivoAdjuntoBase(SQLModel):
    entidad_tipo: str = Field(max_length=50, index=True)  # 'BITACORA', 'GENERADOR', 'CALIDAD'
    entidad_id: int = Field(index=True)
    ruta_archivo: str = Field(max_length=500)
    descripcion_pie_foto: Optional[str] = Field(default=None, max_length=300)


class ArchivoAdjunto(ArchivoAdjuntoBase, table=True):
    __tablename__ = "archivos_adjunto"

    id_archivo_adjunto: Optional[int] = Field(default=None, primary_key=True)
    fecha_carga: datetime = Field(default_factory=datetime.utcnow)


class ArchivoAdjuntoCreate(SQLModel):
    entidad_tipo: Literal["BITACORA", "GENERADOR", "CALIDAD"]
    entidad_id: int
    ruta_archivo: str = Field(max_length=500)
    descripcion_pie_foto: Optional[str] = Field(default=None, max_length=300)


class ArchivoAdjuntoUpdate(SQLModel):
    descripcion_pie_foto: Optional[str] = Field(default=None, max_length=300)


class ArchivoAdjuntoPublic(ArchivoAdjuntoBase):
    id_archivo_adjunto: int
    fecha_carga: datetime


# =====================================================================
# 2. BITÁCORA NOTA (Inmutable / Append-Only)
# =====================================================================
class BitacoraNotaBase(SQLModel):
    id_obra: int = Field(foreign_key="obras.id_obra", index=True)
    id_usuario: int = Field(foreign_key="usuario.id_usuario")
    tipo_nota: str = Field(max_length=50)  # APERTURA, ORDEN, SOLICITUD, SEGUIMIENTO, CIERRE
    asunto: str = Field(max_length=250)
    descripcion: str = Field(sa_column=Column(Text, nullable=False))


class BitacoraNota(BitacoraNotaBase, table=True):
    __tablename__ = "bitacora_notas"

    id_nota: Optional[int] = Field(default=None, primary_key=True)
    consecutivo_nota: int = Field(index=True)
    fecha_registro: datetime = Field(default_factory=datetime.utcnow)
    firmada: bool = Field(default=False)
    sello_digital: Optional[str] = Field(default=None, max_length=255)

    # Relación polimórfica de solo lectura usando sa_relationship_kwargs
    archivos_adjuntos: List[ArchivoAdjunto] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": lambda: and_(
                BitacoraNota.id_nota == foreign(ArchivoAdjunto.entidad_id),
                ArchivoAdjunto.entidad_tipo == "BITACORA"
            ),
            "viewonly": True
        }
    )


class BitacoraNotaCreate(BitacoraNotaBase):
    pass


class BitacoraNotaFirma(SQLModel):
    """Único esquema de actualización permitido: estampado de firma electrónica."""
    sello_digital: str = Field(min_length=10, max_length=255)


class BitacoraNotaPublic(BitacoraNotaBase):
    id_nota: int
    consecutivo_nota: int
    fecha_registro: datetime
    firmada: bool
    sello_digital: Optional[str] = None
    archivos_adjuntos: List[ArchivoAdjuntoPublic] = []


# =====================================================================
# 3. EXPEDIENTE DOCUMENTO (Repositorio Documental)
# =====================================================================
class ExpedienteDocumentoBase(SQLModel):
    id_obra: int = Field(foreign_key="obras.id_obra", index=True)
    fase: str = Field(max_length=100)  # 01_PRELIMINAR, 02_CONTRATACION, 03_EJECUCION, 04_CIERRE
    nombre: str = Field(max_length=250)
    version: int = Field(default=1, ge=1)
    archivo_url: str = Field(max_length=500)
    hash_sha256: str = Field(min_length=64, max_length=64)


class ExpedienteDocumento(ExpedienteDocumentoBase, table=True):
    __tablename__ = "expediente_documentos"

    id_documento: Optional[int] = Field(default=None, primary_key=True)
    estatus: str = Field(default="EN_REVISION", max_length=50)
    fecha_subida: datetime = Field(default_factory=datetime.utcnow)


class ExpedienteDocumentoCreate(ExpedienteDocumentoBase):
    pass


class ExpedienteDocumentoUpdate(SQLModel):
    estatus: Optional[str] = Field(default=None, max_length=50)
    version: Optional[int] = Field(default=None, ge=1)
    archivo_url: Optional[str] = Field(default=None, max_length=500)
    hash_sha256: Optional[str] = Field(default=None, min_length=64, max_length=64)


class ExpedienteDocumentoPublic(ExpedienteDocumentoBase):
    id_documento: int
    estatus: str
    fecha_subida: datetime


# =====================================================================
# 4. CONTROL DE CALIDAD Y PRUEBAS DE LABORATORIO
# =====================================================================
class ControlCalidadPruebaBase(SQLModel):
    id_obra: int = Field(foreign_key="obras.id_obra", index=True)
    id_concepto: int = Field(foreign_key="conceptos_catalogo.id_concepto")
    tipo_ensayo: str = Field(max_length=150)
    fecha_muestreo: date
    resultado_dictamen: str = Field(max_length=100)  # APROBADO, RECHAZADO, CONDICIONADO
    url_reporte_laboratorio: str = Field(max_length=500)


class ControlCalidadPrueba(ControlCalidadPruebaBase, table=True):
    __tablename__ = "control_calidad_pruebas"

    id_prueba: Optional[int] = Field(default=None, primary_key=True)

    archivos_adjuntos: List[ArchivoAdjunto] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": lambda: and_(
                ControlCalidadPrueba.id_prueba == foreign(ArchivoAdjunto.entidad_id),
                ArchivoAdjunto.entidad_tipo == "CALIDAD"
            ),
            "viewonly": True
        }
    )


class ControlCalidadPruebaCreate(ControlCalidadPruebaBase):
    pass


class ControlCalidadPruebaUpdate(SQLModel):
    resultado_dictamen: Optional[str] = Field(default=None, max_length=100)
    url_reporte_laboratorio: Optional[str] = Field(default=None, max_length=500)


class ControlCalidadPruebaPublic(ControlCalidadPruebaBase):
    id_prueba: int
    archivos_adjuntos: List[ArchivoAdjuntoPublic] = []


# =====================================================================
# 5. REPORTE DIARIO DE SUPERVISIÓN
# =====================================================================
class ReporteDiarioSupervisionBase(SQLModel):
    id_obra: int = Field(foreign_key="obras.id_obra", index=True)
    id_supervisor: int = Field(foreign_key="supervisor.id_supervisor")
    fecha_reporte: date
    clima: str = Field(max_length=100)
    estado_fuerza_trabajo: int = Field(default=0, ge=0)
    maquinaria_activa: Optional[str] = Field(default=None, sa_column=Column(Text))
    incidencias_relevantes: Optional[str] = Field(default=None, sa_column=Column(Text))


class ReporteDiarioSupervision(ReporteDiarioSupervisionBase, table=True):
    __tablename__ = "reporte_diario_supervision"

    id_reporte: Optional[int] = Field(default=None, primary_key=True)


class ReporteDiarioSupervisionCreate(ReporteDiarioSupervisionBase):
    pass


class ReporteDiarioSupervisionUpdate(SQLModel):
    clima: Optional[str] = Field(default=None, max_length=100)
    estado_fuerza_trabajo: Optional[int] = Field(default=None, ge=0)
    maquinaria_activa: Optional[str] = None
    incidencias_relevantes: Optional[str] = None


class ReporteDiarioSupervisionPublic(ReporteDiarioSupervisionBase):
    id_reporte: int