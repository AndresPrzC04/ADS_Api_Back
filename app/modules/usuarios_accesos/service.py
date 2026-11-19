from datetime import date, datetime, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from sqlmodel import Session, col, func, or_, select
from app.core.security import get_password_hash
from app.models_base import (
    AuditoriaLogs,
    BitacoraNotas,
    CatCorreosAutorizados,
    CatEstatus,
    Contratistas,
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
# 2. SERVICIO: DICCIONARIO DE CORREOS Y DOMINIOS AUTORIZADOS (RN-ADM-01.8 a RN-ADM-01.11)
# ==========================================
class DiccionarioCorreoService:
    @staticmethod
    def registrar_entrada(
        session: Session,
        entrada_in: models.CorreoAutorizadoCreate,
        admin: Usuarios,
        ip_origen: str
    ) -> CatCorreosAutorizados:
        valor_norm = entrada_in.valor.strip().lower().lstrip("@")
        if entrada_in.tipo_registro == "CORREO" and "@" not in valor_norm:
            raise HTTPException(
                status_code=400,
                detail="Si tipo_registro es 'CORREO', el valor debe ser una dirección de correo válida."
            )
        if entrada_in.tipo_registro == "DOMINIO" and "@" in valor_norm:
            raise HTTPException(
                status_code=400,
                detail="Si tipo_registro es 'DOMINIO', indique únicamente el dominio (ej. 'gob.mx' o 'constructora.com')."
            )

        if entrada_in.id_contratista is not None:
            contratista = session.get(Contratistas, entrada_in.id_contratista)
            if not contratista or not contratista.activo:
                raise HTTPException(status_code=404, detail="Empresa contratista no encontrada o inactiva.")

        existente = session.exec(
            select(CatCorreosAutorizados).where(CatCorreosAutorizados.valor == valor_norm)
        ).first()
        if existente:
            raise HTTPException(
                status_code=400,
                detail=f"El registro '{valor_norm}' ya existe en el diccionario de correos autorizados."
            )

        nuevo = CatCorreosAutorizados(
            id_contratista=entrada_in.id_contratista,
            tipo_registro=entrada_in.tipo_registro,
            valor=valor_norm,
            activo=True
        )
        session.add(nuevo)
        session.commit()
        session.refresh(nuevo)

        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=admin.id_usuario,
            tipo_accion="SEGURIDAD",
            accion_ejecutada=f"ALTA_CORREO_AUTORIZADO_{nuevo.id_correo_autorizado}",
            descripcion=f"Registro en diccionario de correos: {valor_norm} ({entrada_in.tipo_registro})",
            ip_origen=ip_origen
        )
        return nuevo

    @staticmethod
    def listar_entradas(
        session: Session, id_contratista: Optional[int] = None, solo_activos: bool = True
    ) -> List[CatCorreosAutorizados]:
        stmt = select(CatCorreosAutorizados)
        if solo_activos:
            stmt = stmt.where(col(CatCorreosAutorizados.activo).is_(True))
        if id_contratista is not None:
            stmt = stmt.where(CatCorreosAutorizados.id_contratista == id_contratista)
        return list(session.exec(stmt).all())

    @staticmethod
    def desactivar_entrada(
        session: Session, id_correo_autorizado: int, admin: Usuarios, ip_origen: str
    ) -> CatCorreosAutorizados:
        entrada = session.get(CatCorreosAutorizados, id_correo_autorizado)
        if not entrada:
            raise HTTPException(status_code=404, detail="Entrada del diccionario de correos no encontrada.")
        entrada.activo = False
        session.add(entrada)
        session.commit()
        session.refresh(entrada)

        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=admin.id_usuario,
            tipo_accion="SEGURIDAD",
            accion_ejecutada=f"BAJA_CORREO_AUTORIZADO_{id_correo_autorizado}",
            descripcion=f"Baja lógica de registro en diccionario de correos: {entrada.valor}",
            ip_origen=ip_origen
        )
        return entrada

    @staticmethod
    def validar_correo_para_rol(session: Session, correo: str, nombre_rol: str) -> None:
        """
        RN-ADM-01.8, RN-ADM-01.9, RN-ADM-01.10 y RN-ADM-01.11:
        - Roles internos (ADMINISTRADOR, DIRECTIVO, RESIDENTE, SUPERVISOR):
          El correo o su dominio debe estar activo en Cat_Correos_Autorizados con id_contratista IS NULL.
        - Rol SUPERINTENDENTE:
          El correo o su dominio debe estar activo en Cat_Correos_Autorizados vinculado a una empresa
          contratista que tenga al menos un contrato activo (VIGENTE) en Contratos.
        """
        correo_norm = correo.strip().lower()
        dominio = correo_norm.split("@")[-1] if "@" in correo_norm else ""
        rol_upper = nombre_rol.upper()

        if rol_upper == "SUPERINTENDENTE":
            coincidencias = list(
                session.exec(
                    select(CatCorreosAutorizados).where(
                        col(CatCorreosAutorizados.activo).is_(True),
                        col(CatCorreosAutorizados.id_contratista).is_not(None),
                        or_(
                            CatCorreosAutorizados.valor == correo_norm,
                            CatCorreosAutorizados.valor == dominio,
                        ),
                    )
                ).all()
            )
            if not coincidencias:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El correo proporcionado no pertenece al diccionario de correos autorizados de ninguna empresa contratista registrada"
                )

            # RN-ADM-01.11: Verificar que la contratista tenga al menos un contrato activo (VIGENTE)
            est_vigente = session.exec(
                select(CatEstatus).where(CatEstatus.ambito == "CONTRATO", CatEstatus.clave == "VIGENTE")
            ).first()
            tiene_contrato_activo = False
            for c in coincidencias:
                if c.id_contratista is not None and est_vigente:
                    contrato_activo = session.exec(
                        select(Contratos).where(
                            Contratos.id_contratista == c.id_contratista,
                            Contratos.id_estatus == est_vigente.id_estatus
                        )
                    ).first()
                    if contrato_activo:
                        tiene_contrato_activo = True
                        break

            if not tiene_contrato_activo:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "RN-ADM-01.11: La empresa contratista asociada a este correo no cuenta con un contrato "
                        "activo/vigente; no se pueden dar de alta nuevas cuentas operativas."
                    )
                )
        else:
            # Roles internos: ADMINISTRADOR, DIRECTIVO, RESIDENTE, SUPERVISOR (RN-ADM-01.8)
            coincidencia_inst = session.exec(
                select(CatCorreosAutorizados).where(
                    col(CatCorreosAutorizados.activo).is_(True),
                    col(CatCorreosAutorizados.id_contratista).is_(None),
                    or_(
                        CatCorreosAutorizados.valor == correo_norm,
                        CatCorreosAutorizados.valor == dominio,
                    ),
                )
            ).first()
            if not coincidencia_inst:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"RN-ADM-01.8: El correo '{correo_norm}' no pertenece a ningún dominio o correo "
                        f"institucional autorizado para el rol {rol_upper}."
                    )
                )


# ==========================================
# 3. SERVICIO DE GESTIÓN DE USUARIOS Y ROLES (RF-ADM-01 y RF-ADM-02)
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
        correo_str = str(usuario_in.correo).strip().lower()

        # RN-ADM-01.1: Unicidad de correo
        correo_existente = session.exec(
            select(Usuarios).where(Usuarios.correo == correo_str)
        ).first()
        if correo_existente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RN-ADM-01.1: El correo electrónico ya se encuentra registrado en la plataforma."
            )

        rol = session.get(RolUsuario, usuario_in.id_rol_usuario)
        if not rol or not rol.activo:
            raise HTTPException(status_code=404, detail="El rol especificado no existe o está inactivo.")

        # RN-ADM-01.8 a RN-ADM-01.11: Validar correo contra diccionario institucional o de contratista
        DiccionarioCorreoService.validar_correo_para_rol(session, correo_str, rol.nombre)

        # RN-ADM-01.2 y RNF-SEG-01: Hash tanto para contraseña como para firma electrónica
        firma_hash = (
            get_password_hash(usuario_in.firma_electronica)
            if usuario_in.firma_electronica
            else None
        )

        nuevo_usuario = Usuarios(
            id_rol_usuario=usuario_in.id_rol_usuario,
            nombre_completo=usuario_in.nombre_completo,
            correo=correo_str,
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

        rol_objetivo = usuario.rol
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
            rol_objetivo = nuevo_rol
            usuario.id_rol_usuario = usuario_in.id_rol_usuario

        if usuario_in.correo:
            correo_nuevo = str(usuario_in.correo).strip().lower()
            if correo_nuevo != usuario.correo:
                duplicado = session.exec(
                    select(Usuarios).where(Usuarios.correo == correo_nuevo)
                ).first()
                if duplicado:
                    raise HTTPException(status_code=400, detail="RN-ADM-01.1: El correo ya está en uso.")
                if rol_objetivo:
                    DiccionarioCorreoService.validar_correo_para_rol(session, correo_nuevo, rol_objetivo.nombre)
                usuario.correo = correo_nuevo

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

        usuario.activo = False
        session.add(usuario)

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
# 4. SERVICIO DE ASIGNACIONES Y RELEVOS EN OBRA (RF-ADM-03 y RN-ADM-04.2)
# ==========================================
class AsignacionObraService:
    @staticmethod
    def evaluar_activacion_obra(session: Session, id_obra: int) -> str:
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

        asig_saliente.fecha_fin_asignacion = max(relevo_in.fecha_relevo, asig_saliente.fecha_inicio_asignacion)
        session.add(asig_saliente)

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
