from datetime import date, datetime
from typing import List, Optional
from sqlalchemy import String, Integer, Boolean, Date, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class RolUsuario(Base):
    __tablename__ = "rol_usuario"

    id_rol_usuario: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(String(255))

    usuarios: Mapped[List["Usuario"]] = relationship(back_populates="rol")


class Usuario(Base):
    __tablename__ = "usuario"

    id_usuario: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_rol_usuario: Mapped[int] = mapped_column(ForeignKey("rol_usuario.id_rol_usuario"), nullable=False)
    id_empresa_contratista: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    nombre_usuario: Mapped[str] = mapped_column(String(150), nullable=False)
    correo: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    fecha_registro: Mapped[date] = mapped_column(Date, default=func.current_date())
    estado: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relaciones hacia otras entidades del módulo
    rol: Mapped["RolUsuario"] = relationship(back_populates="usuarios")
    obras_asignadas: Mapped[List["UsuarioObra"]] = relationship(back_populates="usuario")
    logs_auditoria: Mapped[List["AuditoriaLog"]] = relationship(back_populates="usuario")

    # Relaciones hacia perfiles específicos (Bloque 05)
    perfil_admin: Mapped[Optional["Administrador"]] = relationship(back_populates="usuario", uselist=False)
    perfil_directivo: Mapped[Optional["Directivo"]] = relationship(back_populates="usuario", uselist=False)
    perfil_superintendente: Mapped[Optional["Superintendente"]] = relationship(back_populates="usuario", uselist=False)
    perfil_supervisor: Mapped[Optional["Supervisor"]] = relationship(back_populates="usuario", uselist=False)
    perfil_residente: Mapped[Optional["Residente"]] = relationship(back_populates="usuario", uselist=False)


class UsuarioObra(Base):
    __tablename__ = "usuarios_obra"

    id_obra: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuario.id_usuario"), primary_key=True)
    fecha_alta: Mapped[date] = mapped_column(Date, default=func.current_date())
    activo_en_obra: Mapped[bool] = mapped_column(Boolean, default=True)

    usuario: Mapped["Usuario"] = relationship(back_populates="obras_asignadas")


class AuditoriaLog(Base):
    __tablename__ = "auditoria_logs"

    id_auditoria: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuario.id_usuario"), nullable=False)
    id_obra: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rol_obra: Mapped[Optional[str]] = mapped_column(String(50))
    ip_origen: Mapped[str] = mapped_column(String(45), default="127.0.0.1")
    accion_ejecutada: Mapped[str] = mapped_column(String(255), nullable=False)
    tabla_afectada: Mapped[str] = mapped_column(String(100), nullable=False)
    registro_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    usuario: Mapped["Usuario"] = relationship(back_populates="logs_auditoria")


# --- Perfiles Especializados (Bloque 05) ---

class Administrador(Base):
    __tablename__ = "administrador"
    id_admin: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuario.id_usuario"), unique=True)
    nivel_acceso: Mapped[str] = mapped_column(String(50), default="TOTAL")

    usuario: Mapped["Usuario"] = relationship(back_populates="perfil_admin")


class Directivo(Base):
    __tablename__ = "directivo"
    id_directivo: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuario.id_usuario"), unique=True)
    area: Mapped[str] = mapped_column(String(100))

    usuario: Mapped["Usuario"] = relationship(back_populates="perfil_directivo")


class Superintendente(Base):
    __tablename__ = "superintendente"
    id_superintendente: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuario.id_usuario"), unique=True)
    zona: Mapped[Optional[str]] = mapped_column(String(100))

    usuario: Mapped["Usuario"] = relationship(back_populates="perfil_superintendente")


class Supervisor(Base):
    __tablename__ = "supervisor"
    id_supervisor: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuario.id_usuario"), unique=True)
    especialidad: Mapped[str] = mapped_column(String(100))

    usuario: Mapped["Usuario"] = relationship(back_populates="perfil_supervisor")


class Residente(Base):
    __tablename__ = "residente"
    id_residente: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuario.id_usuario"), unique=True)

    usuario: Mapped["Usuario"] = relationship(back_populates="perfil_residente")