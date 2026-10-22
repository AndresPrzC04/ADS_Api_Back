from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.core.security import get_password_hash
from . import models, schemas
from app.core.security import get_password_hash, verify_password, create_access_token


# ==========================================
# SERVICIO: AUDITORÍA (Métodos UML)
# ==========================================
class AuditoriaService:
    @staticmethod
    def registrar_evento(db: Session, log_in: schemas.AuditoriaLogCreate) -> models.AuditoriaLog:
        nuevo_log = models.AuditoriaLog(**log_in.model_dump())
        db.add(nuevo_log)
        db.commit()
        db.refresh(nuevo_log)
        return nuevo_log

    @staticmethod
    def consultar_solo_auditor(
        db: Session, id_obra: Optional[int] = None, id_usuario: Optional[int] = None
    ) -> List[models.AuditoriaLog]:
        query = db.query(models.AuditoriaLog)
        if id_obra is not None:
            query = query.filter(models.AuditoriaLog.id_obra == id_obra)
        if id_usuario is not None:
            query = query.filter(models.AuditoriaLog.id_usuario == id_usuario)
        return query.order_by(models.AuditoriaLog.fecha_hora.desc()).all()


# ==========================================
# SERVICIO: ROLES DE USUARIO (Métodos UML)
# ==========================================
class RolUsuarioService:
    @staticmethod
    def crear_rol(db: Session, rol_in: schemas.RolUsuarioCreate) -> models.RolUsuario:
        existente = db.query(models.RolUsuario).filter(models.RolUsuario.nombre == rol_in.nombre.upper()).first()
        if existente:
            raise HTTPException(status_code=400, detail="El rol ya existe.")
        nuevo_rol = models.RolUsuario(
            nombre=rol_in.nombre.upper(),
            descripcion=rol_in.descripcion
        )
        db.add(nuevo_rol)
        db.commit()
        db.refresh(nuevo_rol)
        return nuevo_rol

    @staticmethod
    def consultar_roles(db: Session) -> List[models.RolUsuario]:
        return db.query(models.RolUsuario).all()


# ==========================================
# SERVICIO: USUARIOS (Métodos UML)
# ==========================================
class UsuarioService:
    @staticmethod
    def crear(db: Session, usuario_in: schemas.UsuarioCreate, admin_ejecutor_id: Optional[int] = None) -> models.Usuario:
        # 1. Validar que el correo no esté duplicado
        if db.query(models.Usuario).filter(models.Usuario.correo == usuario_in.correo).first():
            raise HTTPException(status_code=400, detail="El correo electrónico ya está registrado.")

        # 2. Validar que el rol exista
        rol = db.query(models.RolUsuario).filter(models.RolUsuario.id_rol_usuario == usuario_in.id_rol_usuario).first()
        if not rol:
            raise HTTPException(status_code=404, detail="El Rol especificado no existe.")

        # 3. Crear instancia de Usuario con contraseña encriptada
        nuevo_usuario = models.Usuario(
            nombre_usuario=usuario_in.nombre_usuario,
            correo=usuario_in.correo,
            password_hash=get_password_hash(usuario_in.password),
            id_rol_usuario=usuario_in.id_rol_usuario,
            id_empresa_contratista=usuario_in.id_empresa_contratista,
            estado=True
        )
        db.add(nuevo_usuario)
        db.flush()  # Obtiene el id_usuario antes del commit final

        # 4. Crear registro automático en la tabla de perfil del Bloque 05 según el rol
        nombre_rol = rol.nombre.upper()
        if nombre_rol == "ADMINISTRADOR":
            db.add(models.Administrador(id_usuario=nuevo_usuario.id_usuario, nivel_acceso="TOTAL"))
        elif nombre_rol == "DIRECTIVO":
            db.add(models.Directivo(id_usuario=nuevo_usuario.id_usuario, area=usuario_in.area_directivo or "General"))
        elif nombre_rol == "SUPERINTENDENTE":
            db.add(models.Superintendente(id_usuario=nuevo_usuario.id_usuario, zona=usuario_in.zona_superintendente))
        elif nombre_rol == "SUPERVISOR":
            db.add(models.Supervisor(id_usuario=nuevo_usuario.id_usuario, especialidad=usuario_in.especialidad_supervisor or "General"))
        elif nombre_rol == "RESIDENTE":
            db.add(models.Residente(id_usuario=nuevo_usuario.id_usuario))

        db.commit()
        db.refresh(nuevo_usuario)

        # 5. Registrar en AuditoriaLog
        AuditoriaService.registrar_evento(
            db,
            schemas.AuditoriaLogCreate(
                id_usuario=admin_ejecutor_id or nuevo_usuario.id_usuario,
                accion_ejecutada=f"CREACION_USUARIO ({nombre_rol})",
                tabla_afectada="usuario",
                registro_id=nuevo_usuario.id_usuario
            )
        )
        return nuevo_usuario

    @staticmethod
    def consultar(db: Session, skip: int = 0, limit: int = 100) -> List[models.Usuario]:
        return db.query(models.Usuario).offset(skip).limit(limit).all()

    @staticmethod
    def obtener_por_id(db: Session, id_usuario: int) -> models.Usuario:
        usuario = db.query(models.Usuario).filter(models.Usuario.id_usuario == id_usuario).first()
        if not usuario:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
        return usuario

    @staticmethod
    def actualizar(db: Session, id_usuario: int, usuario_in: schemas.UsuarioUpdate) -> models.Usuario:
        usuario = UsuarioService.obtener_por_id(db, id_usuario)
        datos_actualizados = usuario_in.model_dump(exclude_unset=True)
        for campo, valor in datos_actualizados.items():
            setattr(usuario, campo, valor)
        db.commit()
        db.refresh(usuario)
        return usuario

    @staticmethod
    def suspender(db: Session, id_usuario: int) -> models.Usuario:
        usuario = UsuarioService.obtener_por_id(db, id_usuario)
        usuario.estado = False
        db.commit()
        db.refresh(usuario)
        return usuario

    @staticmethod
    def asignar_rol(db: Session, id_usuario: int, nuevo_id_rol: int) -> models.Usuario:
        usuario = UsuarioService.obtener_por_id(db, id_usuario)
        rol = db.query(models.RolUsuario).filter(models.RolUsuario.id_rol_usuario == nuevo_id_rol).first()
        if not rol:
            raise HTTPException(status_code=404, detail="El Rol asignado no existe.")
        usuario.id_rol_usuario = nuevo_id_rol
        db.commit()
        db.refresh(usuario)
        return usuario

    @staticmethod
    def autenticar(db: Session, correo: str, password: str, ip_origen: str = "127.0.0.1") -> schemas.TokenResponse:
        usuario = db.query(models.Usuario).filter(models.Usuario.correo == correo).first()
        if not usuario or not verify_password(password, usuario.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Correo electrónico o contraseña incorrectos.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not usuario.estado:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Esta cuenta se encuentra suspendida."
            )

        nombre_rol = usuario.rol.nombre.upper()
        token_jwt = create_access_token(
            data={"sub": str(usuario.id_usuario), "rol": nombre_rol, "correo": usuario.correo}
        )

        # Registrar inicio de sesión en AuditoriaLog
        AuditoriaService.registrar_evento(
            db,
            schemas.AuditoriaLogCreate(
                id_usuario=usuario.id_usuario,
                ip_origen=ip_origen,
                accion_ejecutada="LOGIN_EXITOSO",
                tabla_afectada="usuario",
                registro_id=usuario.id_usuario
            )
        )

        return schemas.TokenResponse(
            access_token=token_jwt,
            id_usuario=usuario.id_usuario,
            nombre_usuario=usuario.nombre_usuario,
            rol=nombre_rol
        )


# ==========================================
# SERVICIO: ASIGNACIÓN USUARIO-OBRA (Métodos UML)
# ==========================================
class UsuarioObraService:
    @staticmethod
    def vincular(db: Session, asignacion_in: schemas.UsuarioObraCreate) -> models.UsuarioObra:
        UsuarioService.obtener_por_id(db, asignacion_in.id_usuario)
        existente = db.query(models.UsuarioObra).filter(
            models.UsuarioObra.id_obra == asignacion_in.id_obra,
            models.UsuarioObra.id_usuario == asignacion_in.id_usuario
        ).first()

        if existente:
            existente.activo_en_obra = True
            db.commit()
            db.refresh(existente)
            return existente

        nueva_asignacion = models.UsuarioObra(**asignacion_in.model_dump())
        db.add(nueva_asignacion)
        db.commit()
        db.refresh(nueva_asignacion)
        return nueva_asignacion

    @staticmethod
    def desvincular(db: Session, id_obra: int, id_usuario: int) -> models.UsuarioObra:
        asignacion = db.query(models.UsuarioObra).filter(
            models.UsuarioObra.id_obra == id_obra,
            models.UsuarioObra.id_usuario == id_usuario
        ).first()
        if not asignacion:
            raise HTTPException(status_code=404, detail="Asignación no encontrada para esta obra.")
        asignacion.activo_en_obra = False
        db.commit()
        db.refresh(asignacion)
        return asignacion

    @staticmethod
    def consultar_por_obra(db: Session, id_obra: int) -> List[models.UsuarioObra]:
        return db.query(models.UsuarioObra).filter(models.UsuarioObra.id_obra == id_obra).all()