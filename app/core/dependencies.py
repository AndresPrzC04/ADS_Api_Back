from typing import List
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import decode_access_token
from app.modules.usuarios_accesos import models

# Configura el botón "Authorize" en Swagger UI apuntando al endpoint de login
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/usuarios-accesos/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> models.Usuario:
    """Valida el JWT y devuelve la instancia del Usuario autenticado y activo."""
    payload = decode_access_token(token)
    id_usuario: int = payload.get("sub")
    if id_usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales de autenticación inválidas.",
        )

    usuario = db.query(models.Usuario).filter(models.Usuario.id_usuario == int(id_usuario)).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="El usuario no existe.")

    if not usuario.estado:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Su cuenta de usuario ha sido suspendida por el Administrador."
        )
    return usuario


class RequerirRoles:
    """
    Dependencia parametrizable para restringir endpoints por Rol (RBAC).
    Uso: Depends(RequerirRoles(["ADMINISTRADOR", "RESIDENTE"]))
    """
    def __init__(self, roles_permitidos: List[str]):
        self.roles_permitidos = [r.upper() for r in roles_permitidos]

    def __call__(self, current_user: models.Usuario = Depends(get_current_user)) -> models.Usuario:
        nombre_rol = current_user.rol.nombre.upper() if current_user.rol else ""
        if nombre_rol not in self.roles_permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado. Rol actual '{nombre_rol}'. Se requiere uno de: {self.roles_permitidos}"
            )
        return current_user


# Instancias listas para inyectar en los routers de cada módulo
solo_admin = RequerirRoles(["ADMINISTRADOR"])
solo_directivo_o_admin = RequerirRoles(["ADMINISTRADOR", "DIRECTIVO"])
solo_superintendente = RequerirRoles(["SUPERINTENDENTE"])
solo_supervisor = RequerirRoles(["SUPERVISOR"])
solo_residente = RequerirRoles(["RESIDENTE"])
roles_operativos_obra = RequerirRoles(["RESIDENTE", "SUPERVISOR", "SUPERINTENDENTE"])
todos_los_roles = RequerirRoles(["ADMINISTRADOR", "DIRECTIVO", "RESIDENTE", "SUPERVISOR", "SUPERINTENDENTE"])


def verificar_participacion_en_obra(
    id_obra: int,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user)
) -> models.Usuario:
    """
    Cumple RF-ADM-03: Verifica que Residente, Supervisor o Superintendente estén
    activamente vinculados a la obra en la tabla UsuarioObra.
    Administrador y Directivo tienen visibilidad global.
    """
    nombre_rol = current_user.rol.nombre.upper()
    if nombre_rol in ["ADMINISTRADOR", "DIRECTIVO"]:
        return current_user

    asignacion = db.query(models.UsuarioObra).filter(
        models.UsuarioObra.id_obra == id_obra,
        models.UsuarioObra.id_usuario == current_user.id_usuario,
        models.UsuarioObra.activo_en_obra == True
    ).first()

    if not asignacion:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No tienes una asignación activa en la obra con ID {id_obra}."
        )
    return current_user