from datetime import date, datetime, timezone
from typing import Optional
from fastapi import HTTPException, status
from sqlmodel import Session, col, func, or_, select
from app.core.security import get_password_hash
from app.models_base import (
    AuditoriaLogs,
    BitacoraNotas,
    CatEstatus,
    Contratos,
    Estimaciones,
    Obras,
    ObrasAsignaciones,
    Polizas,
    RevisionEstimaciones,
    RolUsuario,
    TipoAccion,
    Usuarios,
)
from . import models


# ==========================================
# 1. SERVICIO DE AUDITORÍA EN 3NF (RNF-SEG-03)
# ==========================================
class AuditoriaService:
    @staticmethod
    def registrar_evento(
        session: Session,
        id_usuario: int,
        tipo_accion: str,
        accion_ejecutada: str,
        descripcion: str,
        id_obra: Optional[int] = None,
        ip_origen: str = "127.0.0.1"
    ) -> AuditoriaLogs:
        accion = session.exec(
            select(TipoAccion).where(TipoAccion.accion_ejecutada == accion_ejecutada)
        ).first()
        if not accion:
            accion = TipoAccion(
                tipo_accion=tipo_accion,
                accion_ejecutada=accion_ejecutada,
                descripcion=descripcion,
                activo=True
            )
            session.add(accion)
            session.commit()
            session.refresh(accion)

        ahora = datetime.now(timezone.utc)
        nuevo_log = AuditoriaLogs(
            id_obra=id_obra,
            id_usuario=id_usuario,
            id_accion=accion.id_accion,
            ip_origen=ip_origen,
            fecha_inicio=ahora,
            fecha_cierre=ahora
        )
        session.add(nuevo_log)
        session.commit()
        session.refresh(nuevo_log)
        return nuevo_log


# ==========================================
# 2. SERVICIO DE GESTIÓN DE USUARIOS Y ROLES (RF-ADM-01 y RF-ADM-02)
# ==========================================
class UsuarioService:
    @staticmethod
    def _contar_admins_activos(session: Session) -> int:
        return session.exec(
            select(func.count(col(Usuarios.id_usuario)))
            .join(RolUsuario)
            .where(RolUsuario.nombre == "ADMINISTRADOR", col(Usuarios.activo).is_(True))
        ).one()

    @staticmethod
    def _usuario_tiene_historial_o_asignacion(session: Session, id_usuario: int) -> bool:
        """RN-ADM-02.2: Verifica si el usuario tiene asignaciones o historial en bitácora/estimaciones."""
        tiene_asignacion = session.exec(
            select(ObrasAsignaciones).where(ObrasAsignaciones.id_usuario == id_usuario)
        ).first()
        tiene_bitacora = session.exec(
            select(BitacoraNotas).where(BitacoraNotas.id_usuario == id_usuario)
        ).first()
        tiene_estimacion = session.exec(
            select(Estimaciones).where(Estimaciones.id_superintendente == id_usuario)
        ).first()
        tiene_revision = session.exec(
            select(RevisionEstimaciones).where(RevisionEstimaciones.id_supervisor == id_usuario)
        ).first()
        return any([tiene_asignacion, tiene_bitacora, tiene_estimacion, tiene_revision])

    @staticmethod
    def crear(
        session: Session, usuario_in: models.UsuarioCreate, admin_actual: Usuarios, ip_origen: str
    ) -> Usuarios:
        # RN-ADM-01.1: Unicidad de correo
        correo_existente = session.exec(
            select(Usuarios).where(Usuarios.correo == str(usuario_in.correo))
        ).first()
        if correo_existente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RN-ADM-01.1: El correo electrónico ya se encuentra registrado en la plataforma."
            )

        rol = session.get(RolUsuario, usuario_in.id_rol_usuario)
        if not rol or not rol.activo:
            raise HTTPException(status_code=404, detail="El rol especificado no existe o está inactivo.")

        # RN-ADM-01.2 y RNF-SEG-01: Hash tanto para contraseña como para firma electrónica
        firma_hash = (
            get_password_hash(usuario_in.firma_electronica)
            if usuario_in.firma_electronica
            else None
        )

        nuevo_usuario = Usuarios(
            id_rol_usuario=usuario_in.id_rol_usuario,
            nombre_completo=usuario_in.nombre_completo,
            correo=str(usuario_in.correo),
            password_hash=get_password_hash(usuario_in.password),
            firma_electronica=firma_hash,
            activo=True
        )
        session.add(nuevo_usuario)
        session.commit()
        session.refresh(nuevo_usuario)

        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=admin_actual.id_usuario,
            tipo_accion="CREACION",
            accion_ejecutada="ALTA_USUARIO",
            descripcion=f"Alta de usuario {nuevo_usuario.correo} con rol {rol.nombre}",
            ip_origen=ip_origen
        )
        return nuevo_usuario

    @staticmethod
    def modificar(
        session: Session,
        id_usuario: int,
        usuario_in: models.UsuarioUpdate,
        admin_actual: Usuarios,
        ip_origen: str
    ) -> Usuarios:
        usuario = session.get(Usuarios, id_usuario)
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")

        # Validaciones si se intenta cambiar el rol (RN-ADM-01.5, RN-ADM-01.6, RN-ADM-02.2)
        if usuario_in.id_rol_usuario is not None and usuario_in.id_rol_usuario != usuario.id_rol_usuario:
            if usuario.id_usuario == admin_actual.id_usuario:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="RN-ADM-01.6: Un Administrador no puede cambiar su propio rol."
                )

            if usuario.rol and usuario.rol.nombre.upper() == "ADMINISTRADOR":
                if UsuarioService._contar_admins_activos(session) <= 1:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="RN-ADM-01.5: No se puede cambiar el rol del último Administrador activo."
                    )

            if UsuarioService._usuario_tiene_historial_o_asignacion(session, id_usuario):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "RN-ADM-02.2: Bloqueado. El usuario ya cuenta con asignaciones o firmas históricas "
                        "en Bitácora/Estimaciones. Suspenda esta cuenta y cree una nueva para el nuevo rol."
                    )
                )
            nuevo_rol = session.get(RolUsuario, usuario_in.id_rol_usuario)
            if not nuevo_rol or not nuevo_rol.activo:
                raise HTTPException(status_code=404, detail="El nuevo rol especificado no existe o está inactivo.")
            usuario.id_rol_usuario = usuario_in.id_rol_usuario

        if usuario_in.correo and str(usuario_in.correo) != usuario.correo:
            duplicado = session.exec(
                select(Usuarios).where(Usuarios.correo == str(usuario_in.correo))
            ).first()
            if duplicado:
                raise HTTPException(status_code=400, detail="RN-ADM-01.1: El correo ya está en uso.")
            usuario.correo = str(usuario_in.correo)

        if usuario_in.nombre_completo:
            usuario.nombre_completo = usuario_in.nombre_completo
        if usuario_in.password:
            usuario.password_hash = get_password_hash(usuario_in.password)
        if usuario_in.firma_electronica:
            usuario.firma_electronica = get_password_hash(usuario_in.firma_electronica)

        session.add(usuario)
        session.commit()
        session.refresh(usuario)

        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=admin_actual.id_usuario,
            tipo_accion="MODIFICACION",
            accion_ejecutada="ACTUALIZACION_USUARIO",
            descripcion=f"Modificación de datos del usuario ID {id_usuario}",
            ip_origen=ip_origen
        )
        return usuario

    @staticmethod
    def suspender(
        session: Session, id_usuario: int, admin_actual: Usuarios, ip_origen: str
    ) -> dict:
        """
        RN-ADM-01.3 a RN-ADM-01.7: Suspensión lógica, validación de quórum de Admin
        y disparo en cascada de Vacante Operativa en obras activas.
        """
        if id_usuario == admin_actual.id_usuario:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RN-ADM-01.6: Un Administrador autenticado no puede suspender su propia cuenta."
            )

        usuario = session.get(Usuarios, id_usuario)
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")

        if not usuario.activo:
            raise HTTPException(status_code=400, detail="El usuario ya se encuentra inactivo.")

        if usuario.rol and usuario.rol.nombre.upper() == "ADMINISTRADOR":
            if UsuarioService._contar_admins_activos(session) <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="RN-ADM-01.5: El sistema requiere mínimo 1 Administrador activo. Dé de alta un suplente primero."
                )

        # 1. Suspensión lógica (RN-ADM-01.3)
        usuario.activo = False
        session.add(usuario)

        # 2. Efecto en cascada sobre asignaciones vigentes (RN-ADM-01.4 y RN-ADM-03.4)
        hoy = date.today()
        asignaciones_activas = list(
            session.exec(
                select(ObrasAsignaciones).where(
                    ObrasAsignaciones.id_usuario == id_usuario,
                    or_(
                        col(ObrasAsignaciones.fecha_fin_asignacion).is_(None),
                        col(ObrasAsignaciones.fecha_fin_asignacion) >= hoy,
                    ),
                )
            ).all()
        )

        estatus_vacante = session.exec(
            select(CatEstatus).where(
                CatEstatus.ambito == "OBRA",
                CatEstatus.clave == "ALERTA_VACANTE_OPERATIVA"
            )
        ).first()

        obras_afectadas = []
        for asig in asignaciones_activas:
            asig.fecha_fin_asignacion = hoy
            session.add(asig)
            obra = session.get(Obras, asig.id_obra)
            if obra and estatus_vacante:
                est_actual = session.get(CatEstatus, obra.id_estatus)
                if not est_actual or est_actual.clave not in {"FINIQUITADA", "CERRADA"}:
                    obra.id_estatus = estatus_vacante.id_estatus
                    session.add(obra)
                    obras_afectadas.append(obra.id_obra)

        session.commit()

        rol_afectado = usuario.rol.nombre if usuario.rol else "SIN_ROL"
        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=admin_actual.id_usuario,
            tipo_accion="SEGURIDAD",
            accion_ejecutada="SUSPENSION_USUARIO",
            descripcion=f"Suspensión lógica de usuario {usuario.correo}. Obras en vacante: {obras_afectadas}",
            ip_origen=ip_origen
        )

        return {
            "mensaje": f"Usuario '{usuario.nombre_completo}' suspendido lógicamente (RN-ADM-01.3).",
            "rol_afectado": rol_afectado,
            "obras_en_alerta_vacante_operativa": obras_afectadas,
            "alerta_vacante": (
                f"Requiere suplente de: {rol_afectado} en obras {obras_afectadas}"
                if obras_afectadas else "El usuario no tenía obras activas asignadas."
            )
        }


# ==========================================
# 3. SERVICIO DE ASIGNACIONES Y RELEVOS EN OBRA (RF-ADM-03 y RN-ADM-04.2)
# ==========================================
class AsignacionObraService:
    @staticmethod
    def evaluar_activacion_obra(session: Session, id_obra: int) -> str:
        """
        RN-ADM-04.2 y RF-SYS-02: Verifica si la obra tiene Contrato, Pólizas y sus 3 actores operativos
        (Residente, Supervisor, Superintendente) activos para pasarla a EN_EJECUCION.
        Respeta si la obra se encuentra SUSPENDIDA o FINIQUITADA/CERRADA.
        """
        obra = session.get(Obras, id_obra)
        if not obra:
            return "NO_ENCONTRADA"

        est_actual = session.get(CatEstatus, obra.id_estatus)
        if est_actual and est_actual.clave in {"SUSPENDIDA", "FINIQUITADA", "CERRADA"}:
            return est_actual.clave

        hoy = date.today()
        asignaciones = list(
            session.exec(
                select(ObrasAsignaciones).where(
                    ObrasAsignaciones.id_obra == id_obra,
                    col(ObrasAsignaciones.fecha_inicio_asignacion) <= hoy,
                    or_(
                        col(ObrasAsignaciones.fecha_fin_asignacion).is_(None),
                        col(ObrasAsignaciones.fecha_fin_asignacion) >= hoy,
                    ),
                )
            ).all()
        )

        roles_presentes = set()
        for a in asignaciones:
            usr = session.get(Usuarios, a.id_usuario)
            if usr and usr.activo and usr.rol:
                roles_presentes.add(usr.rol.nombre.upper())

        tiene_triada = {"RESIDENTE", "SUPERVISOR", "SUPERINTENDENTE"}.issubset(roles_presentes)
        contrato = session.exec(select(Contratos).where(Contratos.id_obra == id_obra)).first()
        tiene_poliza = False
        if contrato:
            poliza = session.exec(select(Polizas).where(Polizas.id_contrato == contrato.id_contrato)).first()
            tiene_poliza = poliza is not None

        if tiene_triada and contrato and tiene_poliza:
            est_eje = session.exec(
                select(CatEstatus).where(CatEstatus.ambito == "OBRA", CatEstatus.clave == "EN_EJECUCION")
            ).first()
            if est_eje:
                obra.id_estatus = est_eje.id_estatus
                session.add(obra)
                session.commit()
                return "EN_EJECUCION"
        return est_actual.clave if est_actual else "EN_CONFIGURACION"

    @staticmethod
    def asignar_usuario_a_obra(
        session: Session, asig_in: models.ObraAsignacionCreate, admin_actual: Usuarios, ip_origen: str
    ) -> ObrasAsignaciones:
        obra = session.get(Obras, asig_in.id_obra)
        if not obra:
            raise HTTPException(status_code=404, detail="La obra especificada no existe.")

        usuario = session.get(Usuarios, asig_in.id_usuario)
        if not usuario or not usuario.activo:
            raise HTTPException(status_code=400, detail="El usuario no existe o se encuentra inactivo.")

        rol_nombre = usuario.rol.nombre.upper() if usuario.rol else ""
        if rol_nombre not in ["RESIDENTE", "SUPERVISOR", "SUPERINTENDENTE"]:
            raise HTTPException(
                status_code=400,
                detail="RF-ADM-03: Solo se pueden vincular usuarios operativos (Residente, Supervisor, Superintendente)."
            )

        # RN-ADM-03.2: Unicidad por área en la obra (no puede haber 2 del mismo rol activos simultáneamente)
        hoy = date.today()
        asignaciones_vigentes = list(
            session.exec(
                select(ObrasAsignaciones).where(
                    ObrasAsignaciones.id_obra == asig_in.id_obra,
                    col(ObrasAsignaciones.fecha_inicio_asignacion) <= hoy,
                    or_(
                        col(ObrasAsignaciones.fecha_fin_asignacion).is_(None),
                        col(ObrasAsignaciones.fecha_fin_asignacion) >= hoy,
                    ),
                )
            ).all()
        )

        for a in asignaciones_vigentes:
            u_actual = session.get(Usuarios, a.id_usuario)
            if u_actual and u_actual.activo and u_actual.rol and u_actual.rol.nombre.upper() == rol_nombre:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"RN-ADM-03.2: La obra ya cuenta con un {rol_nombre} activo ({u_actual.nombre_completo}). "
                        "Utilice el endpoint de relevo operativo para sustituirlo."
                    )
                )

        fecha_fin = asig_in.fecha_fin_asignacion or obra.fecha_fin
        if fecha_fin < asig_in.fecha_inicio_asignacion:
            raise HTTPException(
                status_code=400,
                detail="La fecha de fin de asignación no puede ser anterior a la fecha de inicio."
            )

        nueva_asig = ObrasAsignaciones(
            id_obra=asig_in.id_obra,
            id_usuario=asig_in.id_usuario,
            fecha_inicio_asignacion=asig_in.fecha_inicio_asignacion,
            fecha_fin_asignacion=fecha_fin
        )
        session.add(nueva_asig)
        session.commit()
        session.refresh(nueva_asig)

        # Evaluar si con esta asignación se completa la plantilla o se resuelve una vacante (RN-ADM-04.2)
        AsignacionObraService.evaluar_activacion_obra(session, asig_in.id_obra)

        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=admin_actual.id_usuario,
            id_obra=asig_in.id_obra,
            tipo_accion="ASIGNACION",
            accion_ejecutada="VINCULACION_PERSONAL_OBRA",
            descripcion=f"Asignación de {rol_nombre} (ID {usuario.id_usuario}) a Obra {obra.id_obra}",
            ip_origen=ip_origen
        )
        return nueva_asig

    @staticmethod
    def desvincular_usuario_de_obra(
        session: Session, id_asignacion: int, admin_actual: Usuarios, ip_origen: str
    ) -> dict:
        """
        RN-ADM-03.4: Desvincula a un usuario operativo de una obra específica sin suspender su cuenta,
        registra fecha_fin_asignacion = hoy y pasa la obra a ALERTA_VACANTE_OPERATIVA.
        """
        asig = session.get(ObrasAsignaciones, id_asignacion)
        if not asig:
            raise HTTPException(status_code=404, detail="Asignación no encontrada.")

        obra = session.get(Obras, asig.id_obra)
        usuario = session.get(Usuarios, asig.id_usuario)
        rol_nombre = usuario.rol.nombre.upper() if usuario and usuario.rol else "OPERATIVO"

        hoy = date.today()
        asig.fecha_fin_asignacion = hoy if hoy >= asig.fecha_inicio_asignacion else asig.fecha_inicio_asignacion
        session.add(asig)

        est_vacante = session.exec(
            select(CatEstatus).where(
                CatEstatus.ambito == "OBRA",
                CatEstatus.clave == "ALERTA_VACANTE_OPERATIVA"
            )
        ).first()
        if obra and est_vacante:
            obra.id_estatus = est_vacante.id_estatus
            session.add(obra)

        session.commit()

        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=admin_actual.id_usuario,
            id_obra=asig.id_obra,
            tipo_accion="VACANTE",
            accion_ejecutada="DESVINCULACION_PERSONAL_OBRA",
            descripcion=f"Baja en obra {asig.id_obra} de {rol_nombre} ({usuario.correo if usuario else ''})",
            ip_origen=ip_origen
        )

        return {
            "mensaje": "Usuario desvinculado de la obra (RN-ADM-03.4).",
            "id_obra": asig.id_obra,
            "estado_obra": "ALERTA_VACANTE_OPERATIVA",
            "alerta_sistema": f"Requiere suplente de: {rol_nombre}"
        }

    @staticmethod
    def ejecutar_relevo_operativo(
        session: Session, relevo_in: models.RelevoOperativoCreate, admin_actual: Usuarios, ip_origen: str
    ) -> dict:
        """
        RN-ADM-03.5 a RN-ADM-03.7: Corte histórico en Obras_asignaciones sin borrar al saliente,
        alta del entrante con fecha fin = fecha fin de la obra y registro obligatorio en Auditoría.
        """
        obra = session.get(Obras, relevo_in.id_obra)
        if not obra:
            raise HTTPException(status_code=404, detail="Obra no encontrada.")

        u_saliente = session.get(Usuarios, relevo_in.id_usuario_saliente)
        u_entrante = session.get(Usuarios, relevo_in.id_usuario_entrante)
        if not u_saliente or not u_entrante or not u_entrante.activo:
            raise HTTPException(status_code=400, detail="Verifique que ambos usuarios existan y el entrante esté activo.")

        if u_saliente.id_rol_usuario != u_entrante.id_rol_usuario:
            raise HTTPException(
                status_code=400,
                detail="El usuario entrante debe poseer exactamente el mismo rol que el usuario saliente."
            )

        asig_saliente = session.exec(
            select(ObrasAsignaciones).where(
                ObrasAsignaciones.id_obra == relevo_in.id_obra,
                ObrasAsignaciones.id_usuario == relevo_in.id_usuario_saliente
            ).order_by(col(ObrasAsignaciones.id_asignacion).desc())
        ).first()

        if not asig_saliente:
            raise HTTPException(status_code=404, detail="No se encontró asignación del usuario saliente en esta obra.")

        # RN-ADM-03.5: Actualizar fecha_fin_asignacion del saliente sin borrarlo
        asig_saliente.fecha_fin_asignacion = max(relevo_in.fecha_relevo, asig_saliente.fecha_inicio_asignacion)
        session.add(asig_saliente)

        # RN-ADM-03.5: Insertar nueva asignación para el entrante hasta fecha_fin de la obra
        nueva_asig = ObrasAsignaciones(
            id_obra=obra.id_obra,
            id_usuario=u_entrante.id_usuario,
            fecha_inicio_asignacion=relevo_in.fecha_relevo,
            fecha_fin_asignacion=max(obra.fecha_fin, relevo_in.fecha_relevo)
        )
        session.add(nueva_asig)
        session.commit()
        session.refresh(nueva_asig)

        estado_obra = AsignacionObraService.evaluar_activacion_obra(session, obra.id_obra)

        # RN-ADM-03.7: Registro obligatorio en Auditoría indicando qué Administrador ejecutó el relevo
        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=admin_actual.id_usuario,
            id_obra=obra.id_obra,
            tipo_accion="RELEVO",
            accion_ejecutada="RELEVO_PERSONAL_OPERATIVO",
            descripcion=(
                f"Relevo en Obra {obra.id_obra}: Sale {u_saliente.correo} -> Entra {u_entrante.correo}"
            ),
            ip_origen=ip_origen
        )

        return {
            "mensaje": "Relevo operativo ejecutado exitosamente (RN-ADM-03.5 a RN-ADM-03.7).",
            "id_obra": obra.id_obra,
            "usuario_saliente": u_saliente.nombre_completo,
            "usuario_entrante": u_entrante.nombre_completo,
            "fecha_corte_historico": relevo_in.fecha_relevo,
            "estado_actual_obra": estado_obra
        }
