from datetime import date
from typing import List
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select
from app.core.database import get_session
from app.core.security import decode_access_token
from app.models_base import ObrasAsignaciones, Usuarios

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/usuarios-accesos/login")


def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session)
) -> Usuarios:
    payload = decode_access_token(token)
    id_usuario_str: str = str(payload.get("sub")) # Revisar
    if not id_usuario_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales de token inválidas.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    usuario = session.get(Usuarios, int(id_usuario_str))
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El usuario asociado al token no existe.",
        )

    # RN-ADM-01.4: Bloqueo inmediato de sesión si el usuario pasa a estado inactivo
    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="RN-ADM-01.4: Su cuenta de usuario se encuentra suspendida o inhabilitada.",
        )

    # RN-DIR-03.1: El rol DIRECTIVO solo tiene autorización para peticiones GET
    nombre_rol = usuario.rol.nombre.upper() if usuario.rol else ""
    if nombre_rol == "DIRECTIVO" and request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="RN-DIR-03.1: El rol DIRECTIVO tiene acceso exclusivo de solo lectura (GET)."
        )

    return usuario


class RequerirRoles:
    def __init__(self, roles_permitidos: List[str]):
        self.roles_permitidos = [r.upper() for r in roles_permitidos]

    def __call__(self, current_user: Usuarios = Depends(get_current_user)) -> Usuarios:
        nombre_rol = current_user.rol.nombre.upper() if current_user.rol else ""
        if nombre_rol not in self.roles_permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado para el rol '{nombre_rol}'. Roles permitidos: {self.roles_permitidos}"
            )
        return current_user


solo_admin = RequerirRoles(["ADMINISTRADOR"])
solo_directivo_o_admin = RequerirRoles(["ADMINISTRADOR", "DIRECTIVO"])
solo_residente = RequerirRoles(["RESIDENTE"])
solo_supervisor = RequerirRoles(["SUPERVISOR"])
solo_superintendente = RequerirRoles(["SUPERINTENDENTE"])
roles_operativos_obra = RequerirRoles(["RESIDENTE", "SUPERVISOR", "SUPERINTENDENTE"])


def verificar_participacion_en_obra(
    id_obra: int,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(get_current_user)
) -> Usuarios:
    """
    RN-ADM-03.1: Administrador y Directivo tienen visibilidad global.
    Residente, Supervisor y Superintendente requieren asignación vigente en Obras_asignaciones.
    """
    nombre_rol = current_user.rol.nombre.upper() if current_user.rol else ""
    if nombre_rol in ["ADMINISTRADOR", "DIRECTIVO"]:
        return current_user

    hoy = date.today()
    asignaciones = session.exec(
        select(ObrasAsignaciones).where(
            ObrasAsignaciones.id_obra == id_obra,
            ObrasAsignaciones.id_usuario == current_user.id_usuario
        )
    ).all()

    asignacion_vigente = next(
        (
            a for a in asignaciones
            if a.fecha_inicio_asignacion <= hoy
            and (a.fecha_fin_asignacion is None or a.fecha_fin_asignacion >= hoy)
        ),
        None
    )

    if not asignacion_vigente:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"RN-ADM-03.1: No tiene una asignación operativa vigente en la obra con ID {id_obra}."
        )
    return current_user
