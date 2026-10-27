from typing import List, Optional
from fastapi import HTTPException, status
from sqlmodel import Session, select
from app.core.security import get_password_hash, verify_password, create_access_token
from . import models


class AuditoriaService:
    @staticmethod
    def registrar_evento(session: Session, log_in: models.AuditoriaLogCreate) -> models.AuditoriaLog:
        nuevo_log = models.AuditoriaLog.model_validate(log_in)
        session.add(nuevo_log)
        session.commit()
        session.refresh(nuevo_log)
        return nuevo_log

    @staticmethod
    def consultar_solo_auditor(
        session: Session, id_obra: Optional[int] = None, id_usuario: Optional[int] = None
    ) -> List[models.AuditoriaLog]:
        query = select(models.AuditoriaLog)
        if id_obra is not None:
            query = query.where(models.AuditoriaLog.id_obra == id_obra)
        if id_usuario is not None:
            query = query.where(models.AuditoriaLog.id_usuario == id_usuario)
        query = query.order_by(models.AuditoriaLog.fecha_hora.desc())
        return session.exec(query).all()


class RolUsuarioService:
    @staticmethod
    def crear_rol(session: Session, rol_in: models.RolUsuarioCreate) -> models.RolUsuario:
        existente = session.exec(
            select(models.RolUsuario).where(models.RolUsuario.nombre == rol_in.nombre.upper())
        ).first()
        if existente:
            raise HTTPException(status_code=400, detail="El rol ya existe.")

        nuevo_rol = models.RolUsuario(
            nombre=rol_in.nombre.upper(),
            descripcion=rol_in.descripcion
        )
        session.add(nuevo_rol)
        session.commit()
        session.refresh(nuevo_rol)
        return nuevo_rol

    @staticmethod
    def consultar_roles(session: Session) -> List[models.RolUsuario]:
        return session.exec(select(models.RolUsuario)).all()


class UsuarioService:
    @staticmethod
    def autenticar(session: Session, correo: str, password: str, ip_origen: str = "127.0.0.1") -> models.TokenResponse:
        usuario = session.exec(select(models.Usuario).where(models.Usuario.correo == correo)).first()
        if not usuario or not verify_password(password, usuario.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Correo electrónico o contraseña incorrectos.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not usuario.estado:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cuenta suspendida.")

        nombre_rol = usuario.rol.nombre.upper() if usuario.rol else "SIN_ROL"
        token = create_access_token(
            data={"sub": str(usuario.id_usuario), "rol": nombre_rol, "correo": usuario.correo}
        )

        AuditoriaService.registrar_evento(
            session,
            models.AuditoriaLogCreate(
                id_usuario=usuario.id_usuario,
                ip_origen=ip_origen,
                accion_ejecutada="LOGIN_EXITOSO",
                tabla_afectada="usuario",
                registro_id=usuario.id_usuario
            )
        )

        return models.TokenResponse(
            access_token=token,
            id_usuario=usuario.id_usuario,
            nombre_usuario=usuario.nombre_usuario,
            rol=nombre_rol
        )

    @staticmethod
    def crear(session: Session, usuario_in: models.UsuarioCreate, admin_ejecutor_id: Optional[int] = None) -> models.Usuario:
        # Validar duplicados y existencia de rol
        if session.exec(select(models.Usuario).where(models.Usuario.correo == usuario_in.correo)).first():
            raise HTTPException(status_code=400, detail="El correo ya se encuentra registrado.")

        rol = session.get(models.RolUsuario, usuario_in.id_rol_usuario)
        if not rol:
            raise HTTPException(status_code=404, detail="El Rol especificado no existe.")

        nuevo_usuario = models.Usuario(
            nombre_usuario=usuario_in.nombre_usuario,
            correo=usuario_in.correo,
            password_hash=get_password_hash(usuario_in.password),
            id_rol_usuario=usuario_in.id_rol_usuario,
            id_empresa_contratista=usuario_in.id_empresa_contratista,
            estado=True
        )
        session.add(nuevo_usuario)
        session.commit()
        session.refresh(nuevo_usuario)

        # Crear perfil correspondiente en Bloque 05
        nombre_rol = rol.nombre.upper()
        if nombre_rol == "ADMINISTRADOR":
            session.add(models.Administrador(id_usuario=nuevo_usuario.id_usuario, nivel_acceso="TOTAL"))
        elif nombre_rol == "DIRECTIVO":
            session.add(models.Directivo(id_usuario=nuevo_usuario.id_usuario, area=usuario_in.area_directivo or "General"))
        elif nombre_rol == "SUPERINTENDENTE":
            session.add(models.Superintendente(id_usuario=nuevo_usuario.id_usuario, zona=usuario_in.zona_superintendente))
        elif nombre_rol == "SUPERVISOR":
            session.add(models.Supervisor(id_usuario=nuevo_usuario.id_usuario, especialidad=usuario_in.especialidad_supervisor or "General"))
        elif nombre_rol == "RESIDENTE":
            session.add(models.Residente(id_usuario=nuevo_usuario.id_usuario))

        session.commit()

        AuditoriaService.registrar_evento(
            session,
            models.AuditoriaLogCreate(
                id_usuario=admin_ejecutor_id or nuevo_usuario.id_usuario,
                accion_ejecutada=f"CREACION_USUARIO ({nombre_rol})",
                tabla_afectada="usuario",
                registro_id=nuevo_usuario.id_usuario
            )
        )
        return nuevo_usuario

    @staticmethod
    def consultar(session: Session, skip: int = 0, limit: int = 100) -> List[models.Usuario]:
        return session.exec(select(models.Usuario).offset(skip).limit(limit)).all()

    @staticmethod
    def obtener_por_id(session: Session, id_usuario: int) -> models.Usuario:
        usuario = session.get(models.Usuario, id_usuario)
        if not usuario:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
        return usuario

    @staticmethod
    def actualizar(session: Session, id_usuario: int, usuario_in: models.UsuarioUpdate) -> models.Usuario:
        usuario = UsuarioService.obtener_por_id(session, id_usuario)
        datos = usuario_in.model_dump(exclude_unset=True)
        for campo, valor in datos.items():
            setattr(usuario, campo, valor)
        session.add(usuario)
        session.commit()
        session.refresh(usuario)
        return usuario

    @staticmethod
    def suspender(session: Session, id_usuario: int) -> models.Usuario:
        usuario = UsuarioService.obtener_por_id(session, id_usuario)
        usuario.estado = False
        session.add(usuario)
        session.commit()
        session.refresh(usuario)
        return usuario


class UsuarioObraService:
    @staticmethod
    def vincular(session: Session, asignacion_in: models.UsuarioObraCreate) -> models.UsuarioObra:
        UsuarioService.obtener_por_id(session, asignacion_in.id_usuario)
        existente = session.exec(
            select(models.UsuarioObra).where(
                models.UsuarioObra.id_obra == asignacion_in.id_obra,
                models.UsuarioObra.id_usuario == asignacion_in.id_usuario
            )
        ).first()

        if existente:
            existente.activo_en_obra = True
            session.add(existente)
            session.commit()
            session.refresh(existente)
            return existente

        nueva_asignacion = models.UsuarioObra.model_validate(asignacion_in)
        session.add(nueva_asignacion)
        session.commit()
        session.refresh(nueva_asignacion)
        return nueva_asignacion

    @staticmethod
    def desvincular(session: Session, id_obra: int, id_usuario: int) -> models.UsuarioObra:
        asignacion = session.exec(
            select(models.UsuarioObra).where(
                models.UsuarioObra.id_obra == id_obra,
                models.UsuarioObra.id_usuario == id_usuario
            )
        ).first()
        if not asignacion:
            raise HTTPException(status_code=404, detail="Asignación no encontrada.")
        asignacion.activo_en_obra = False
        session.add(asignacion)
        session.commit()
        session.refresh(asignacion)
        return asignacion

    @staticmethod
    def consultar_por_obra(session: Session, id_obra: int) -> List[models.UsuarioObra]:
        return session.exec(
            select(models.UsuarioObra).where(models.UsuarioObra.id_obra == id_obra)
        ).all()