from datetime import date, datetime
from typing import List, Optional
from pydantic import EmailStr
from sqlmodel import SQLModel, Field, Relationship


# =====================================================================
# 1. ROL DE USUARIO
# =====================================================================
class RolUsuarioBase(SQLModel):
    nombre: str = Field(unique=True, index=True, max_length=50)
    descripcion: Optional[str] = Field(default=None, max_length=255)


class RolUsuario(RolUsuarioBase, table=True):
    __tablename__ = "rol_usuario"

    id_rol_usuario: Optional[int] = Field(default=None, primary_key=True)

    # Relación inversa hacia Usuario
    usuarios: List["Usuario"] = Relationship(back_populates="rol")


class RolUsuarioCreate(RolUsuarioBase):
    pass


class RolUsuarioUpdate(SQLModel):
    nombre: Optional[str] = Field(default=None, max_length=50)
    descripcion: Optional[str] = Field(default=None, max_length=255)


class RolUsuarioPublic(RolUsuarioBase):
    id_rol_usuario: int


# =====================================================================
# 2. USUARIO
# =====================================================================
class UsuarioBase(SQLModel):
    nombre_usuario: str = Field(max_length=150)
    correo: EmailStr = Field(unique=True, index=True, max_length=150)
    id_rol_usuario: int = Field(foreign_key="rol_usuario.id_rol_usuario")
    id_empresa_contratista: Optional[int] = Field(default=None)


class Usuario(UsuarioBase, table=True):
    __tablename__ = "usuario"

    id_usuario: Optional[int] = Field(default=None, primary_key=True)
    password_hash: str = Field(max_length=255)
    fecha_registro: date = Field(default_factory=date.today)
    estado: bool = Field(default=True)

    # Relaciones nativas de SQLModel
    rol: Optional[RolUsuario] = Relationship(back_populates="usuarios")
    obras_asignadas: List["UsuarioObra"] = Relationship(back_populates="usuario")
    logs_auditoria: List["AuditoriaLog"] = Relationship(back_populates="usuario")

    # Subperfiles especializados (Bloque 05)
    perfil_admin: Optional["Administrador"] = Relationship(back_populates="usuario")
    perfil_directivo: Optional["Directivo"] = Relationship(back_populates="usuario")
    perfil_superintendente: Optional["Superintendente"] = Relationship(back_populates="usuario")
    perfil_supervisor: Optional["Supervisor"] = Relationship(back_populates="usuario")
    perfil_residente: Optional["Residente"] = Relationship(back_populates="usuario")


class UsuarioCreate(UsuarioBase):
    password: str = Field(min_length=8)
    area_directivo: Optional[str] = None
    zona_superintendente: Optional[str] = None
    especialidad_supervisor: Optional[str] = None


class UsuarioUpdate(SQLModel):
    nombre_usuario: Optional[str] = Field(default=None, max_length=150)
    correo: Optional[EmailStr] = None
    id_rol_usuario: Optional[int] = None
    id_empresa_contratista: Optional[int] = None
    estado: Optional[bool] = None


class UsuarioPublic(UsuarioBase):
    id_usuario: int
    fecha_registro: date
    estado: bool
    rol: Optional[RolUsuarioPublic] = None


# =====================================================================
# 3. ASIGNACIÓN USUARIO - OBRA (UsuarioObra)
# =====================================================================
class UsuarioObraBase(SQLModel):
    id_obra: int = Field(primary_key=True)
    id_usuario: int = Field(foreign_key="usuario.id_usuario", primary_key=True)


class UsuarioObra(UsuarioObraBase, table=True):
    __tablename__ = "usuarios_obra"

    fecha_alta: date = Field(default_factory=date.today)
    activo_en_obra: bool = Field(default=True)

    usuario: Optional[Usuario] = Relationship(back_populates="obras_asignadas")


class UsuarioObraCreate(UsuarioObraBase):
    pass


class UsuarioObraPublic(UsuarioObraBase):
    fecha_alta: date
    activo_en_obra: bool


# =====================================================================
# 4. AUDITORÍA LOG (Inmutable / Append-Only)
# =====================================================================
class AuditoriaLogBase(SQLModel):
    id_usuario: int = Field(foreign_key="usuario.id_usuario")
    id_obra: Optional[int] = Field(default=None)
    rol_obra: Optional[str] = Field(default=None, max_length=50)
    ip_origen: str = Field(default="127.0.0.1", max_length=45)
    accion_ejecutada: str = Field(max_length=255)
    tabla_afectada: str = Field(max_length=100)
    registro_id: Optional[int] = Field(default=None)


class AuditoriaLog(AuditoriaLogBase, table=True):
    __tablename__ = "auditoria_logs"

    id_auditoria: Optional[int] = Field(default=None, primary_key=True)
    fecha_hora: datetime = Field(default_factory=datetime.utcnow)

    usuario: Optional[Usuario] = Relationship(back_populates="logs_auditoria")


class AuditoriaLogCreate(AuditoriaLogBase):
    pass


class AuditoriaLogPublic(AuditoriaLogBase):
    id_auditoria: int
    fecha_hora: datetime


# =====================================================================
# 5. SUBCLASES DE ROLES (Bloque 05)
# =====================================================================
class Administrador(SQLModel, table=True):
    __tablename__ = "administrador"
    id_admin: Optional[int] = Field(default=None, primary_key=True)
    id_usuario: int = Field(foreign_key="usuario.id_usuario", unique=True)
    nivel_acceso: str = Field(default="TOTAL", max_length=50)

    usuario: Optional[Usuario] = Relationship(back_populates="perfil_admin")


class Directivo(SQLModel, table=True):
    __tablename__ = "directivo"
    id_directivo: Optional[int] = Field(default=None, primary_key=True)
    id_usuario: int = Field(foreign_key="usuario.id_usuario", unique=True)
    area: str = Field(max_length=100)

    usuario: Optional[Usuario] = Relationship(back_populates="perfil_directivo")


class Superintendente(SQLModel, table=True):
    __tablename__ = "superintendente"
    id_superintendente: Optional[int] = Field(default=None, primary_key=True)
    id_usuario: int = Field(foreign_key="usuario.id_usuario", unique=True)
    zona: Optional[str] = Field(default=None, max_length=100)

    usuario: Optional[Usuario] = Relationship(back_populates="perfil_superintendente")


class Supervisor(SQLModel, table=True):
    __tablename__ = "supervisor"
    id_supervisor: Optional[int] = Field(default=None, primary_key=True)
    id_usuario: int = Field(foreign_key="usuario.id_usuario", unique=True)
    especialidad: str = Field(max_length=100)

    usuario: Optional[Usuario] = Relationship(back_populates="perfil_supervisor")


class Residente(SQLModel, table=True):
    __tablename__ = "residente"
    id_residente: Optional[int] = Field(default=None, primary_key=True)
    id_usuario: int = Field(foreign_key="usuario.id_usuario", unique=True)

    usuario: Optional[Usuario] = Relationship(back_populates="perfil_residente")


# =====================================================================
# 6. ESQUEMA DE TOKEN DE AUTENTICACIÓN (JWT)
# =====================================================================
class TokenResponse(SQLModel):
    access_token: str
    token_type: str = "bearer"
    id_usuario: int
    nombre_usuario: str
    rol: str