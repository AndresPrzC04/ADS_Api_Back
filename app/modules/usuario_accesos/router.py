from typing import List, Optional
from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session
from app.core.database import get_session
from app.core.dependencies import solo_admin, get_current_user
from . import models, service

router = APIRouter(prefix="/usuarios-accesos", tags=["01 y 05. Usuarios, Roles y Accesos"])


@router.post("/login", response_model=models.TokenResponse)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session)
):
    ip_origen = request.client.host if request.client else "127.0.0.1"
    return service.UsuarioService.autenticar(
        session, correo=form_data.username, password=form_data.password, ip_origen=ip_origen
    )


@router.get("/mi-perfil", response_model=models.UsuarioPublic)
def mi_perfil(current_user: models.Usuario = Depends(get_current_user)):
    return current_user


@router.post("/roles", response_model=models.RolUsuarioPublic, status_code=status.HTTP_201_CREATED)
def crear_rol(
    rol_in: models.RolUsuarioCreate,
    session: Session = Depends(get_session),
    admin: models.Usuario = Depends(solo_admin)
):
    return service.RolUsuarioService.crear_rol(session, rol_in)


@router.get("/roles", response_model=List[models.RolUsuarioPublic])
def listar_roles(
    session: Session = Depends(get_session),
    admin: models.Usuario = Depends(solo_admin)
):
    return service.RolUsuarioService.consultar_roles(session)


@router.post("/usuarios", response_model=models.UsuarioPublic, status_code=status.HTTP_201_CREATED)
def crear_usuario(
    usuario_in: models.UsuarioCreate,
    session: Session = Depends(get_session),
    admin: models.Usuario = Depends(solo_admin)
):
    return service.UsuarioService.crear(session, usuario_in, admin_ejecutor_id=admin.id_usuario)


@router.get("/usuarios", response_model=List[models.UsuarioPublic])
def listar_usuarios(
    skip: int = 0,
    limit: int = 100,
    session: Session = Depends(get_session),
    admin: models.Usuario = Depends(solo_admin)
):
    return service.UsuarioService.consultar(session, skip=skip, limit=limit)


@router.patch("/usuarios/{id_usuario}", response_model=models.UsuarioPublic)
def actualizar_usuario(
    id_usuario: int,
    usuario_in: models.UsuarioUpdate,
    session: Session = Depends(get_session),
    admin: models.Usuario = Depends(solo_admin)
):
    return service.UsuarioService.actualizar(session, id_usuario, usuario_in)


@router.patch("/usuarios/{id_usuario}/suspender", response_model=models.UsuarioPublic)
def suspender_usuario(
    id_usuario: int,
    session: Session = Depends(get_session),
    admin: models.Usuario = Depends(solo_admin)
):
    return service.UsuarioService.suspender(session, id_usuario)


@router.post("/asignaciones-obra", response_model=models.UsuarioObraPublic, status_code=status.HTTP_201_CREATED)
def vincular_usuario_a_obra(
    asignacion_in: models.UsuarioObraCreate,
    session: Session = Depends(get_session),
    admin: models.Usuario = Depends(solo_admin)
):
    return service.UsuarioObraService.vincular(session, asignacion_in)


@router.patch("/asignaciones-obra/{id_obra}/usuario/{id_usuario}/desvincular", response_model=models.UsuarioObraPublic)
def desvincular_usuario_de_obra(
    id_obra: int,
    id_usuario: int,
    session: Session = Depends(get_session),
    admin: models.Usuario = Depends(solo_admin)
):
    return service.UsuarioObraService.desvincular(session, id_obra, id_usuario)


@router.get("/auditoria", response_model=List[models.AuditoriaLogPublic])
def consultar_auditoria(
    id_obra: Optional[int] = None,
    id_usuario: Optional[int] = None,
    session: Session = Depends(get_session),
    admin: models.Usuario = Depends(solo_admin)
):
    return service.AuditoriaService.consultar_solo_auditor(session, id_obra=id_obra, id_usuario=id_usuario)