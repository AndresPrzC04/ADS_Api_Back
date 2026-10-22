from datetime import date, datetime
from typing import List, Optional
from sqlalchemy import (
    String, Integer, Boolean, Date, DateTime, Text, ForeignKey, func, and_
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, foreign
from app.core.database import Base


class ArchivoAdjunto(Base):
    __tablename__ = "archivos_adjunto"

    id_archivo_adjunto: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entidad_tipo: Mapped[str] = mapped_column(String(50), nullable=False)  # 'BITACORA', 'GENERADOR', 'CALIDAD'
    entidad_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    ruta_archivo: Mapped[str] = mapped_column(String(500), nullable=False)
    descripcion_pie_foto: Mapped[Optional[str]] = mapped_column(String(300))
    fecha_carga: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BitacoraNota(Base):
    __tablename__ = "bitacora_notas"

    id_nota: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_obra: Mapped[int] = mapped_column(ForeignKey("obras.id_obra"), nullable=False)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuario.id_usuario"), nullable=False)
    consecutivo_nota: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo_nota: Mapped[str] = mapped_column(String(50), nullable=False)  # APERTURA, ORDEN, SOLICITUD, SEGUIMIENTO, CIERRE
    asunto: Mapped[str] = mapped_column(String(250), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    fecha_registro: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Soporte para el método +firmar() del Diagrama de Clases UML
    firmada: Mapped[bool] = mapped_column(Boolean, default=False)
    sello_digital: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relación polimórfica de solo lectura hacia Archivos_adjunto
    archivos_adjuntos: Mapped[List["ArchivoAdjunto"]] = relationship(
        primaryjoin=lambda: and_(
            BitacoraNota.id_nota == foreign(ArchivoAdjunto.entidad_id),
            ArchivoAdjunto.entidad_tipo == "BITACORA"
        ),
        viewonly=True
    )


class ExpedienteDocumento(Base):
    __tablename__ = "expediente_documentos"

    id_documento: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_obra: Mapped[int] = mapped_column(ForeignKey("obras.id_obra"), nullable=False)
    fase: Mapped[str] = mapped_column(String(100), nullable=False)  # PRELIMINAR, LICITACION, EJECUCION, CIERRE
    nombre: Mapped[str] = mapped_column(String(250), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    archivo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    estatus: Mapped[str] = mapped_column(String(50), default="EN_REVISION")  # BORRADOR, EN_REVISION, APROBADO
    fecha_subida: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ControlCalidadPrueba(Base):
    __tablename__ = "control_calidad_pruebas"

    id_prueba: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_obra: Mapped[int] = mapped_column(ForeignKey("obras.id_obra"), nullable=False)
    id_concepto: Mapped[int] = mapped_column(ForeignKey("conceptos_catalogo.id_concepto"), nullable=False)
    tipo_ensayo: Mapped[str] = mapped_column(String(150), nullable=False)
    fecha_muestreo: Mapped[date] = mapped_column(Date, nullable=False)
    resultado_dictamen: Mapped[str] = mapped_column(String(100), nullable=False)  # APROBADO, RECHAZADO, CONDICIONADO
    url_reporte_laboratorio: Mapped[str] = mapped_column(String(500), nullable=False)

    archivos_adjuntos: Mapped[List["ArchivoAdjunto"]] = relationship(
        primaryjoin=lambda: and_(
            ControlCalidadPrueba.id_prueba == foreign(ArchivoAdjunto.entidad_id),
            ArchivoAdjunto.entidad_tipo == "CALIDAD"
        ),
        viewonly=True
    )


class ReporteDiarioSupervision(Base):
    __tablename__ = "reporte_diario_supervision"

    id_reporte: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_obra: Mapped[int] = mapped_column(ForeignKey("obras.id_obra"), nullable=False)
    id_supervisor: Mapped[int] = mapped_column(ForeignKey("supervisor.id_supervisor"), nullable=False)
    fecha_reporte: Mapped[date] = mapped_column(Date, nullable=False)
    clima: Mapped[str] = mapped_column(String(100), nullable=False)
    estado_fuerza_trabajo: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    maquinaria_activa: Mapped[Optional[str]] = mapped_column(Text)
    incidencias_relevantes: Mapped[Optional[str]] = mapped_column(Text)