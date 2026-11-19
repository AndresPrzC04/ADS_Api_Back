from datetime import date, datetime
from typing import Literal, Optional
from pydantic import EmailStr
from sqlmodel import Field, SQLModel


# ==========================================
# 1. ESQUEMAS DE ROLES Y USUARIOS (RF-ADM-01, RF-ADM-02)
# ==========================================
class RolUsuarioPublic(SQLModel):
    id_rol_usuario: int
    nombre: str
    descripcion: Optional[str] = None
    activo: bool


class UsuarioCreate(SQLModel):
    id_rol_usuario: int
    nombre_completo: str = Field(max_length=255)
    correo: EmailStr = Field(max_length=150)
    password: str = Field(min_length=8)
    firma_electronica: Optional[str] = Field(default=None, min_length=6, max_length=255)


class UsuarioUpdate(SQLModel):
    nombre_completo: Optional[str] = Field(default=None, max_length=255)
    correo: Optional[EmailStr] = Field(default=None, max_length=150)
    password: Optional[str] = Field(default=None, min_length=8)
    firma_electronica: Optional[str] = Field(default=None, min_length=6, max_length=255)
    id_rol_usuario: Optional[int] = None


class UsuarioPublic(SQLModel):
    id_usuario: int
    id_rol_usuario: int
    nombre_completo: str
    correo: EmailStr
    activo: bool
    rol: Optional[RolUsuarioPublic] = None


class TokenResponse(SQLModel):
    access_token: str
    token_type: str = "bearer"
    expira_en_minutos: int = 20
    id_usuario: int
    nombre_completo: str
    correo: str
    rol: str


# ==========================================
# 2. DICCIONARIO DE CORREOS Y DOMINIOS AUTORIZADOS (RN-ADM-01.8 a RN-ADM-01.11)
# ==========================================
class CorreoAutorizadoCreate(SQLModel):
    id_contratista: Optional[int] = None  # None = Institucional interno; ID = Empresa contratista
    tipo_registro: Literal["DOMINIO", "CORREO"]
    valor: str = Field(max_length=150)


class CorreoAutorizadoPublic(SQLModel):
    id_correo_autorizado: int
    id_contratista: Optional[int] = None
    tipo_registro: str
    valor: str
    activo: bool


# ==========================================
# 3. ESQUEMAS DE ASIGNACIÓN Y RELEVO EN OBRAS (RF-ADM-03)
# ==========================================
class ObraAsignacionCreate(SQLModel):
    id_obra: int
    id_usuario: int
    fecha_inicio_asignacion: date = Field(default_factory=date.today)
    fecha_fin_asignacion: Optional[date] = None


class RelevoOperativoCreate(SQLModel):
    id_obra: int
    id_usuario_saliente: int
    id_usuario_entrante: int
    fecha_relevo: date = Field(default_factory=date.today)


class ObraAsignacionPublic(SQLModel):
    id_asignacion: int
    id_obra: int
    id_usuario: int
    fecha_inicio_asignacion: date
    fecha_fin_asignacion: Optional[date] = None


# ==========================================
# 4. ESQUEMAS DE CATÁLOGOS MAESTROS (RF-ADM-05)
# ==========================================
class UnidadMedidaCreate(SQLModel):
    clave: str = Field(max_length=20)
    nombre: str = Field(max_length=100)


class UnidadMedidaPublic(UnidadMedidaCreate):
    id_unidad: int
    activo: bool


class TipoConceptoCreate(SQLModel):
    clave: str = Field(max_length=30)
    nombre: str = Field(max_length=100)
    requiere_apu: bool = False


class TipoConceptoPublic(TipoConceptoCreate):
    id_tipo_concepto: int
    activo: bool


class TipoEstimacionCreate(SQLModel):
    clave: str = Field(max_length=40)
    nombre: str = Field(max_length=100)
    descripcion: Optional[str] = None


class TipoEstimacionPublic(TipoEstimacionCreate):
    id_tipo_estimacion: int
    activo: bool


class TipoPolizaCreate(SQLModel):
    clave: str = Field(max_length=50)
    nombre: str = Field(max_length=100)


class TipoPolizaPublic(TipoPolizaCreate):
    id_tipo_poliza: int
    activo: bool


class EstatusCreate(SQLModel):
    ambito: str = Field(max_length=30)
    clave: str = Field(max_length=50)
    nombre: str = Field(max_length=100)


class EstatusPublic(EstatusCreate):
    id_estatus: int
    activo: bool


class TipoNotaBitacoraCreate(SQLModel):
    clave: str = Field(max_length=50)
    nombre: str = Field(max_length=120)
    id_rol_exclusivo: Optional[int] = None
    min_imagenes: int = 0


class TipoNotaBitacoraPublic(TipoNotaBitacoraCreate):
    id_tipo_nota: int
    activo: bool


class TipoEnsayoCreate(SQLModel):
    clave: str = Field(max_length=40)
    nombre: str = Field(max_length=150)
    norma_referencia: Optional[str] = Field(default=None, max_length=100)


class TipoEnsayoPublic(TipoEnsayoCreate):
    id_tipo_ensayo: int
    activo: bool


# ==========================================
# 5. ESQUEMAS DE AUDITORÍA (RNF-SEG-03)
# ==========================================
class AuditoriaLogPublic(SQLModel):
    id_log: int
    id_obra: Optional[int] = None
    id_usuario: int
    id_accion: int
    ip_origen: Optional[str] = None
    fecha_inicio: datetime
    fecha_cierre: datetime
