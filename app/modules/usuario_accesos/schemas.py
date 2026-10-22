from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict, Field


# ==========================================
# 1. ESQUEMAS: ROL USUARIO
# ==========================================
class RolUsuarioBase(BaseModel):
    nombre: str = Field(..., max_length=50, examples=["ADMINISTRADOR", "RESIDENTE"])
    descripcion: Optional[str] = Field(None, max_length=255)


class RolUsuarioCreate(RolUsuarioBase):
    pass


class RolUsuarioUpdate(BaseModel):
    nombre: Optional[str] = Field(None, max_length=50)
    descripcion: Optional[str] = Field(None, max_length=255)


class RolUsuarioPublic(RolUsuarioBase):
    id_rol_usuario: int
    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 2. ESQUEMAS: USUARIO
# ==========================================
class UsuarioBase(BaseModel):
    nombre_usuario: str = Field(..., max_length=150)
    correo: EmailStr
    id_rol_usuario: int
    id_empresa_contratista: Optional[int] = None


class UsuarioCreate(UsuarioBase):
    password: str = Field(..., min_length=8, description="Contraseña en texto plano al crear cuenta")
    # Datos opcionales para inicializar su perfil del Bloque 05 automáticamente
    area_directivo: Optional[str] = None
    zona_superintendente: Optional[str] = None
    especialidad_supervisor: Optional[str] = None


class UsuarioUpdate(BaseModel):
    nombre_usuario: Optional[str] = Field(None, max_length=150)
    correo: Optional[EmailStr] = None
    id_rol_usuario: Optional[int] = None
    id_empresa_contratista: Optional[int] = None
    estado: Optional[bool] = None


class UsuarioPublic(UsuarioBase):
    id_usuario: int
    fecha_registro: date
    estado: bool
    rol: Optional[RolUsuarioPublic] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 3. ESQUEMAS: USUARIO OBRA (ASIGNACIONES)
# ==========================================
class UsuarioObraBase(BaseModel):
    id_usuario: int
    id_obra: int


class UsuarioObraCreate(UsuarioObraBase):
    pass


class UsuarioObraUpdate(BaseModel):
    activo_en_obra: bool


class UsuarioObraPublic(UsuarioObraBase):
    fecha_alta: date
    activo_en_obra: bool

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 4. ESQUEMAS: AUDITORIA LOG (APPEND-ONLY)
# ==========================================
class AuditoriaLogBase(BaseModel):
    id_usuario: int
    id_obra: Optional[int] = None
    rol_obra: Optional[str] = None
    ip_origen: str = "127.0.0.1"
    accion_ejecutada: str
    tabla_afectada: str
    registro_id: Optional[int] = None


class AuditoriaLogCreate(AuditoriaLogBase):
    pass


class AuditoriaLogPublic(AuditoriaLogBase):
    id_auditoria: int
    fecha_hora: datetime

    model_config = ConfigDict(from_attributes=True)

# ==========================================
# 5. ESQUEMA: RESPUESTA DE LOGIN (JWT)
# ==========================================
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    id_usuario: int
    nombre_usuario: str
    rol: str