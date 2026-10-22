from typing import List, Optional
from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import solo_admin, get_current_user
from . import schemas, service, models

router = APIRouter(prefix="/usuarios-accesos", tags=["01 y 05. Usuarios, Roles y Accesos"])


# --- Endpoint Público de Autenticación (OAuth2 Login) ---
@router.post("/login", response_model=schemas.TokenResponse)
def iniciar_sesion(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    En Swagger UI ingresa el 'correo' en el campo 'username' y tu contraseña en 'password'.
    """
    ip_cliente = request.client.host if request.client else "127.0.0.1"
    return service.UsuarioService.autenticar(
        db, correo=form_data.username, password=form_data.password, ip_origen=ip_cliente
    )


@router.get("/mi-perfil", response_model=schemas.UsuarioPublic)
def obtener_mi_perfil(current_user: models.Usuario = Depends(get_current_user)):
    return current_user


# --- Endpoints Exclusivos del Administrador (RF-ADM-01 a RF-ADM-03) ---
@router.post("/roles", response_model=schemas.RolUsuarioPublic, status_code=status.HTTP_201_CREATED)
def crear_rol(
    rol_in: schemas.RolUsuarioCreate,
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(solo_admin)
):
    return service.RolUsuarioService.crear_rol(db, rol_in)


@router.get("/roles", response_model=List[schemas.RolUsuarioPublic])
def listar_roles(
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(solo_admin)
):
    return service.RolUsuarioService.consultar_roles(db)


@router.post("/usuarios", response_model=schemas.UsuarioPublic, status_code=status.HTTP_201_CREATED)
def crear_usuario(
    usuario_in: schemas.UsuarioCreate,
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(solo_admin)
):
    return service.UsuarioService.crear(db, usuario_in, admin_ejecutor_id=admin.id_usuario)


@router.get("/usuarios", response_model=List[schemas.UsuarioPublic])
def listar_usuarios(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(solo_admin)
):
    return service.UsuarioService.consultar(db, skip=skip, limit=limit)


@router.patch("/usuarios/{id_usuario}/suspender", response_model=schemas.UsuarioPublic)
def suspender_usuario(
    id_usuario: int,
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(solo_admin)
):
    return service.UsuarioService.suspender(db, id_usuario)


@router.post("/asignaciones-obra", response_model=schemas.UsuarioObraPublic, status_code=status.HTTP_201_CREATED)
def vincular_usuario_a_obra(
    asignacion_in: schemas.UsuarioObraCreate,
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(solo_admin)
):
    return service.UsuarioObraService.vincular(db, asignacion_in)


@router.get("/auditoria", response_model=List[schemas.AuditoriaLogPublic])
def consultar_bitacora_auditoria(
    id_obra: Optional[int] = None,
    id_usuario: Optional[int] = None,
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(solo_admin)
):
    return service.AuditoriaService.consultar_solo_auditor(db, id_obra=id_obra, id_usuario=id_usuario)