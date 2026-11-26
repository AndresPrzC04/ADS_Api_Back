from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import List
from fastapi import HTTPException, status
from sqlmodel import Session, col, func, select
from app.core.security import (
    validar_firma_electronica_y_generar_sello,
    validar_formato_y_tamano_archivo,
)
from app.models_base import (
    AvancesFisicos,
    BitacoraNotas,
    CatEstatus,
    CatTipoEnsayo,
    CatTipoNotaBitacora,
    Contratos,
    ControlCalidadPruebas,
    EvidenciaAdjunta,
    ObraConceptos,
    Obras,
    ReporteDiarioSupervision,
    ReporteIncidentes,
    Usuarios,
)
from app.modules.obras_contratos.service import DirectivoFiniquitoService
from app.modules.usuarios_accesos.service import AuditoriaService
from . import models

TIPOS_PERMITIDOS_POR_ROL = {
    "RESIDENTE": {
        "APERTURA",
        "ORDEN_TRABAJO",
        "AUTORIZACION_ADICIONALES",
        "SUSPENSION_TEMPORAL",
        "REANUDACION",
        "CIERRE",
    },
    "SUPERINTENDENTE": {
        "SOLICITUD",
        "INCIDENTE_OPERATIVO",
        "RESPUESTA",
        "AVISO_TERMINACION",
    },
    "SUPERVISOR": {
        "SEGUIMIENTO",
        "INCIDENCIA_CAMPO",
        "ACUERDO_JUNTA",
        "DICTAMEN_CALIDAD",
    },
}


# ==========================================
# 1. SERVICIO: BITÁCORA ELECTRÓNICA INMUTABLE Y RECALENDARIZACIÓN CONTRACTUAL
# ==========================================
class BitacoraService:
    @staticmethod
    def _verificar_bitacora_no_cerrada(session: Session, id_obra: int) -> None:
        tipo_cierre = session.exec(
            select(CatTipoNotaBitacora).where(CatTipoNotaBitacora.clave == "CIERRE")
        ).first()
        if tipo_cierre:
            cierre_firmado = session.exec(
                select(BitacoraNotas).where(
                    BitacoraNotas.id_obra == id_obra,
                    BitacoraNotas.id_tipo_nota == tipo_cierre.id_tipo_nota,
                    col(BitacoraNotas.firmada).is_(True)
                )
            ).first()
            if cierre_firmado:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="La bitácora del contrato se encuentra cerrada y congelada"
                )

    @staticmethod
    def _enriquecer_nota(session: Session, nota: BitacoraNotas) -> models.BitacoraNotaPublic:
        tipo = session.get(CatTipoNotaBitacora, nota.id_tipo_nota)
        evidencias = list(
            session.exec(
                select(EvidenciaAdjunta).where(EvidenciaAdjunta.id_nota == nota.id_nota)
            ).all()
        )
        return models.BitacoraNotaPublic(
            id_nota=nota.id_nota,
            id_obra=nota.id_obra,
            id_usuario=nota.id_usuario,
            id_tipo_nota=nota.id_tipo_nota,
            clave_tipo_nota=tipo.clave if tipo else None,
            consecutivo_nota=nota.consecutivo_nota,
            asunto=nota.asunto,
            descripcion=nota.descripcion,
            fecha_registro=nota.fecha_registro,
            firmada=nota.firmada,
            sello_digital=nota.sello_digital,
            evidencias=[models.EvidenciaAdjuntaPublic(**e.model_dump()) for e in evidencias]
        )

    @staticmethod
    def crear_nota(
        session: Session,
        nota_in: models.BitacoraNotaCreate,
        usuario: Usuarios,
        ip_origen: str
    ) -> models.BitacoraNotaPublic:
        obra = session.get(Obras, nota_in.id_obra)
        if not obra:
            raise HTTPException(status_code=404, detail="La obra especificada no existe.")

        BitacoraService._verificar_bitacora_no_cerrada(session, obra.id_obra)

        est_obra = session.get(CatEstatus, obra.id_estatus)
        clave_est_obra = est_obra.clave if est_obra else ""
        if clave_est_obra in {"EN_CONFIGURACION", "ALERTA_VACANTE_OPERATIVA"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"RN-ADM-04.3: No se permite abrir ni operar la bitácora mientras la obra "
                    f"se encuentre en estado '{clave_est_obra}'."
                )
            )

        rol_nombre = usuario.rol.nombre.upper() if usuario.rol else ""
        clave_tipo = nota_in.clave_tipo_nota.strip().upper()

        permitidos = TIPOS_PERMITIDOS_POR_ROL.get(rol_nombre, set())
        if clave_tipo not in permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"El rol '{rol_nombre}' no tiene autorización para emitir notas de tipo '{clave_tipo}'. "
                    f"Tipos permitidos: {sorted(permitidos)}"
                )
            )

        tipo_cat = session.exec(
            select(CatTipoNotaBitacora).where(
                CatTipoNotaBitacora.clave == clave_tipo,
                col(CatTipoNotaBitacora.activo).is_(True)
            )
        ).first()
        if not tipo_cat:
            raise HTTPException(status_code=404, detail=f"El tipo de nota '{clave_tipo}' no existe en el catálogo.")

        ultimo_consecutivo = session.exec(
            select(func.max(col(BitacoraNotas.consecutivo_nota))).where(BitacoraNotas.id_obra == obra.id_obra)
        ).one() or 0

        if ultimo_consecutivo == 0:
            if clave_tipo != "APERTURA" or rol_nombre != "RESIDENTE":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "RN-RES-01.1: Ningún actor puede crear notas si la obra no cuenta con la "
                        "nota consecutiva #1 de tipo 'APERTURA' emitida por el Residente."
                    )
                )
        else:
            if clave_tipo == "APERTURA":
                raise HTTPException(
                    status_code=400,
                    detail="La obra ya cuenta con su Nota #1 de Apertura de Bitácora."
                )
            nota_uno = session.exec(
                select(BitacoraNotas).where(
                    BitacoraNotas.id_obra == obra.id_obra,
                    BitacoraNotas.consecutivo_nota == 1
                )
            ).first()
            if not nota_uno or not nota_uno.firmada:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="RN-RES-01.1: La Nota #1 de APERTURA debe estar firmada electrónicamente por el Residente."
                )

        if nota_in.id_obra_concepto_adicional is not None and nota_in.cantidad_adicional_autorizada is not None:
            if rol_nombre != "RESIDENTE":
                raise HTTPException(
                    status_code=403,
                    detail="RN-RES-02.1: Solo el Residente puede autorizar cantidades adicionales en catálogo."
                )
            conc = session.get(ObraConceptos, nota_in.id_obra_concepto_adicional)
            if not conc or conc.id_obra != obra.id_obra:
                raise HTTPException(status_code=404, detail="Concepto de obra para cantidad adicional no encontrado.")
            conc.cantidad_adicional_autorizada += nota_in.cantidad_adicional_autorizada
            session.add(conc)

        nueva_nota = BitacoraNotas(
            id_obra=obra.id_obra,
            id_usuario=usuario.id_usuario,
            id_tipo_nota=tipo_cat.id_tipo_nota,
            consecutivo_nota=int(ultimo_consecutivo) + 1,
            asunto=nota_in.asunto,
            descripcion=nota_in.descripcion,
            firmada=False,
            sello_digital=None
        )
        session.add(nueva_nota)
        session.commit()
        session.refresh(nueva_nota)

        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=usuario.id_usuario,
            id_obra=obra.id_obra,
            tipo_accion="CREACION",
            accion_ejecutada=f"CREACION_NOTA_BITACORA_{nueva_nota.id_nota}",
            descripcion=f"Creación de nota #{nueva_nota.consecutivo_nota} ({clave_tipo})",
            ip_origen=ip_origen
        )
        return BitacoraService._enriquecer_nota(session, nueva_nota)

    @staticmethod
    def firmar_nota(
        session: Session,
        id_nota: int,
        firma_in: models.BitacoraNotaFirmaInput,
        usuario: Usuarios,
        ip_origen: str
    ) -> models.BitacoraNotaPublic:
        nota = session.get(BitacoraNotas, id_nota)
        if not nota:
            raise HTTPException(status_code=404, detail="Nota de bitácora no encontrada.")

        BitacoraService._verificar_bitacora_no_cerrada(session, nota.id_obra)

        if nota.firmada:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RNF-SEG-02 / RN-SUPT-05.3: Esta nota ya fue firmada electrónicamente y es inmutable."
            )

        if nota.id_usuario != usuario.id_usuario:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo el autor que registró la nota puede estampar su firma electrónica en ella."
            )

        tipo_cat = session.get(CatTipoNotaBitacora, nota.id_tipo_nota)
        clave_tipo = tipo_cat.clave if tipo_cat else ""

        if tipo_cat and tipo_cat.min_imagenes > 0:
            total_fotos = session.exec(
                select(func.count(col(EvidenciaAdjunta.id_evidencia))).where(
                    EvidenciaAdjunta.id_nota == nota.id_nota
                )
            ).one()
            if total_fotos < tipo_cat.min_imagenes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"RN-SUPT-05.2: La nota de '{clave_tipo}' requiere mínimo {tipo_cat.min_imagenes} "
                        f"fotografías válidas adjuntas antes de poder firmarse (actuales: {total_fotos})."
                    )
                )

        sello = validar_firma_electronica_y_generar_sello(
            firma_plana=firma_in.firma_electronica,
            firma_hash_usuario=usuario.firma_electronica,
            id_usuario=usuario.id_usuario,
            referencia=f"BITACORA-OBRA:{nota.id_obra}-NOTA:{nota.consecutivo_nota}"
        )

        nota.firmada = True
        nota.sello_digital = sello
        session.add(nota)

        obra = session.get(Obras, nota.id_obra)

        # RN-RES-02.2 / RF-SYS-01: Suspensión y Reanudación sobre fecha_fin de Obras (sin Gantt)
        if clave_tipo == "SUSPENSION_TEMPORAL" and obra:
            est_susp = session.exec(
                select(CatEstatus).where(CatEstatus.ambito == "OBRA", CatEstatus.clave == "SUSPENDIDA")
            ).first()
            if est_susp:
                obra.id_estatus = est_susp.id_estatus
                session.add(obra)

        elif clave_tipo == "REANUDACION" and obra:
            tipo_susp = session.exec(
                select(CatTipoNotaBitacora).where(CatTipoNotaBitacora.clave == "SUSPENSION_TEMPORAL")
            ).first()
            ultima_susp = None
            if tipo_susp:
                ultima_susp = session.exec(
                    select(BitacoraNotas)
                    .where(
                        BitacoraNotas.id_obra == obra.id_obra,
                        BitacoraNotas.id_tipo_nota == tipo_susp.id_tipo_nota,
                        col(BitacoraNotas.firmada).is_(True)
                    )
                    .order_by(col(BitacoraNotas.consecutivo_nota).desc())
                ).first()

            fecha_susp = ultima_susp.fecha_registro.date() if ultima_susp else date.today()
            fecha_rean = nota.fecha_registro.date()
            delta_dias = max(1, (fecha_rean - fecha_susp).days)

            obra.fecha_fin = obra.fecha_fin + timedelta(days=delta_dias)
            est_eje = session.exec(
                select(CatEstatus).where(CatEstatus.ambito == "OBRA", CatEstatus.clave == "EN_EJECUCION")
            ).first()
            if est_eje:
                obra.id_estatus = est_eje.id_estatus
            session.add(obra)

        elif clave_tipo == "CIERRE" and obra:
            est_cerrada = session.exec(
                select(CatEstatus).where(CatEstatus.ambito == "OBRA", CatEstatus.clave == "FINIQUITADA")
            ).first()
            if est_cerrada:
                obra.id_estatus = est_cerrada.id_estatus
                session.add(obra)
            contrato = session.exec(select(Contratos).where(Contratos.id_obra == obra.id_obra)).first()
            est_cont_fin = session.exec(
                select(CatEstatus).where(CatEstatus.ambito == "CONTRATO", CatEstatus.clave == "FINIQUITADO")
            ).first()
            if contrato and est_cont_fin:
                contrato.id_estatus = est_cont_fin.id_estatus
                session.add(contrato)

        session.commit()
        session.refresh(nota)

        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=usuario.id_usuario,
            id_obra=nota.id_obra,
            tipo_accion="FIRMA",
            accion_ejecutada=f"FIRMA_NOTA_BITACORA_{nota.id_nota}",
            descripcion=f"Firma electrónica de nota #{nota.consecutivo_nota} ({clave_tipo})",
            ip_origen=ip_origen
        )
        return BitacoraService._enriquecer_nota(session, nota)

    @staticmethod
    def consultar_paginado(
        session: Session, id_obra: int, skip: int = 0, limit: int = 20
    ) -> List[models.BitacoraNotaPublic]:
        limit_seguro = min(max(1, limit), 100)
        notas = list(
            session.exec(
                select(BitacoraNotas)
                .where(BitacoraNotas.id_obra == id_obra)
                .order_by(col(BitacoraNotas.consecutivo_nota).asc())
                .offset(max(0, skip))
                .limit(limit_seguro)
            ).all()
        )
        return [BitacoraService._enriquecer_nota(session, n) for n in notas]


# ==========================================
# 2. SERVICIO: EVIDENCIA FOTOGRÁFICA ADJUNTA (Bitácora o Reporte de Supervisión)
# ==========================================
class EvidenciaService:
    @staticmethod
    def agregar_evidencia(
        session: Session, ev_in: models.EvidenciaAdjuntaCreate
    ) -> EvidenciaAdjunta:
        tiene_nota = ev_in.id_nota is not None
        tiene_reporte = ev_in.id_reporte is not None
        if tiene_nota == tiene_reporte:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debe vincular la evidencia exactamente a una nota de bitácora (id_nota) o a un reporte de supervisión (id_reporte), no a ambos."
            )

        validar_formato_y_tamano_archivo(ev_in.ruta_archivo, (".pdf", ".jpg", ".jpeg", ".png"))

        if ev_in.id_nota is not None:
            nota = session.get(BitacoraNotas, ev_in.id_nota)
            if not nota:
                raise HTTPException(status_code=404, detail="Nota de bitácora no encontrada.")
            BitacoraService._verificar_bitacora_no_cerrada(session, nota.id_obra)
            if nota.firmada:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="RN-SUPT-05.3 / RNF-SEG-02: No se pueden agregar evidencias a una nota de bitácora ya firmada."
                )
        elif ev_in.id_reporte is not None:
            reporte = session.get(ReporteDiarioSupervision, ev_in.id_reporte)
            if not reporte:
                raise HTTPException(status_code=404, detail="Reporte de supervisión no encontrado.")
            est_rep = session.get(CatEstatus, reporte.id_estatus_reporte)
            if est_rep and est_rep.clave == "FIRMADO":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="RN-SUP-03.4 / RNF-SEG-02: No se pueden agregar evidencias a un reporte de supervisión ya firmado."
                )

        nueva_ev = EvidenciaAdjunta(
            id_nota=ev_in.id_nota,
            id_reporte=ev_in.id_reporte,
            ruta_archivo=ev_in.ruta_archivo,
            descripcion_pie_foto=ev_in.descripcion_pie_foto
        )
        session.add(nueva_ev)
        session.commit()
        session.refresh(nueva_ev)
        return nueva_ev

    @staticmethod
    def eliminar_evidencia(session: Session, id_evidencia: int) -> dict:
        ev = session.get(EvidenciaAdjunta, id_evidencia)
        if not ev:
            raise HTTPException(status_code=404, detail="Evidencia adjunta no encontrada.")

        if ev.id_nota is not None:
            nota = session.get(BitacoraNotas, ev.id_nota)
            if nota:
                BitacoraService._verificar_bitacora_no_cerrada(session, nota.id_obra)
                if nota.firmada:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="RN-SUPT-05.3 / RNF-SEG-02: Prohibido eliminar evidencias de una nota de bitácora ya firmada."
                    )
        elif ev.id_reporte is not None:
            reporte = session.get(ReporteDiarioSupervision, ev.id_reporte)
            est_rep = session.get(CatEstatus, reporte.id_estatus_reporte) if reporte else None
            if est_rep and est_rep.clave == "FIRMADO":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="RN-SUP-03.4 / RNF-SEG-02: Prohibido eliminar evidencias de un reporte de supervisión ya firmado."
                )

        session.delete(ev)
        session.commit()
        return {"detalle": f"Evidencia {id_evidencia} eliminada correctamente."}


# ==========================================
# 3. SERVICIO: CONTROL DE CALIDAD Y REPORTE DE SUPERVISIÓN CON AVANCE FÍSICO (RF-SUP-03)
# ==========================================
ORDEN_ESTATUS_INCIDENTE = {
    "CREADO": 0,
    "EMITIDO": 1,
    "ATENDIDO": 2,
}


class SupervisionCalidadService:
    @staticmethod
    def _obtener_estatus_reporte_id(session: Session, clave: str) -> int:
        est = session.exec(
            select(CatEstatus).where(CatEstatus.ambito == "REPORTE", CatEstatus.clave == clave)
        ).first()
        if not est:
            raise HTTPException(
                status_code=500,
                detail=f"Estatus de reporte (REPORTE: {clave}) no encontrado en Cat_Estatus."
            )
        return est.id_estatus

    @staticmethod
    def _obtener_estatus_incidente_id(session: Session, clave: str) -> int:
        clave_norm = clave.strip().upper()
        est = session.exec(
            select(CatEstatus).where(CatEstatus.ambito == "INCIDENTE", CatEstatus.clave == clave_norm)
        ).first()
        if not est:
            raise HTTPException(
                status_code=500,
                detail=f"Estatus de incidente (INCIDENTE: {clave_norm}) no encontrado en Cat_Estatus."
            )
        return est.id_estatus

    @staticmethod
    def _obtener_ultimo_avance_financiero(session: Session, id_obra: int) -> Decimal:
        ultimo = session.exec(
            select(AvancesFisicos)
            .where(AvancesFisicos.id_obra == id_obra)
            .order_by(col(AvancesFisicos.id_avance).desc())
        ).first()
        return ultimo.porcentaje_financiero_real if ultimo else Decimal("0.00")

    @staticmethod
    def _enriquecer_incidente(
        session: Session, inc: ReporteIncidentes
    ) -> models.ReporteIncidentePublic:
        est = session.get(CatEstatus, inc.id_estatus_incidente)
        return models.ReporteIncidentePublic(
            id_incidente=inc.id_incidente,
            id_reporte=inc.id_reporte,
            id_estatus_incidente=inc.id_estatus_incidente,
            clave_estatus=est.clave if est else "CREADO",
            suceso=inc.suceso,
            accion_solucion=inc.accion_solucion,
        )

    @staticmethod
    def _sincronizar_incidentes(
        session: Session,
        id_reporte: int,
        incidentes_in: List[models.ReporteIncidenteInput],
    ) -> None:
        existentes = list(
            session.exec(
                select(ReporteIncidentes).where(ReporteIncidentes.id_reporte == id_reporte)
            ).all()
        )
        for inc_prev in existentes:
            session.delete(inc_prev)
        session.flush()

        for item in incidentes_in:
            suceso_norm = item.suceso.strip()
            if not suceso_norm:
                continue
            id_est_inc = SupervisionCalidadService._obtener_estatus_incidente_id(
                session, item.clave_estatus
            )
            nuevo_inc = ReporteIncidentes(
                id_reporte=id_reporte,
                id_estatus_incidente=id_est_inc,
                suceso=suceso_norm,
                accion_solucion=item.accion_solucion.strip() if item.accion_solucion else None,
            )
            session.add(nuevo_inc)

    @staticmethod
    def _enriquecer_reporte(
        session: Session,
        reporte: ReporteDiarioSupervision,
        advertencia_calidad: str | None = None
    ) -> models.ReporteDiarioSupervisionPublic:
        est = session.get(CatEstatus, reporte.id_estatus_reporte)
        clave_est = est.clave if est else "BORRADOR"
        evidencias = list(
            session.exec(
                select(EvidenciaAdjunta).where(EvidenciaAdjunta.id_reporte == reporte.id_reporte)
            ).all()
        )
        incidentes = list(
            session.exec(
                select(ReporteIncidentes)
                .where(ReporteIncidentes.id_reporte == reporte.id_reporte)
                .order_by(col(ReporteIncidentes.id_incidente).asc())
            ).all()
        )
        pct_financiero_actual = SupervisionCalidadService._obtener_ultimo_avance_financiero(
            session, reporte.id_obra
        )
        return models.ReporteDiarioSupervisionPublic(
            id_reporte=reporte.id_reporte,
            id_obra=reporte.id_obra,
            id_supervisor=reporte.id_supervisor,
            fecha_reporte=reporte.fecha_reporte,
            id_estatus_reporte=reporte.id_estatus_reporte,
            estatus_reporte=clave_est,
            actividades_realizadas=reporte.actividades_realizadas,
            clima=reporte.clima,
            horas_lluvia=reporte.horas_lluvia,
            maquinaria_cantidad=reporte.maquinaria_cantidad,
            equipo_cantidad=reporte.equipo_cantidad,
            personal_cantidad=reporte.personal_cantidad,
            porcentaje_avance_reportado=reporte.porcentaje_avance_reportado,
            porcentaje_financiero_actual=pct_financiero_actual,
            firmado=(clave_est == "FIRMADO"),
            sello_digital=reporte.sello_digital,
            fecha_envio=reporte.fecha_envio,
            fecha_firma=reporte.fecha_firma,
            incidentes=[
                SupervisionCalidadService._enriquecer_incidente(session, inc)
                for inc in incidentes
            ],
            evidencias=[models.EvidenciaAdjuntaPublic(**e.model_dump()) for e in evidencias],
            advertencia_calidad=advertencia_calidad
        )

    @staticmethod
    def _validar_progresividad_avance(session: Session, id_obra: int, porcentaje_nuevo: Decimal) -> None:
        """
        RN-SUP-03.6 y RN-DIR-01.7: Verifica que el porcentaje por registrar sea mayor o igual
        al último avance físico registrado en Avances_Fisicos para la obra.
        """
        ultimo_avance = DirectivoFiniquitoService.obtener_ultimo_avance_fisico(session, id_obra)
        if porcentaje_nuevo < ultimo_avance:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Inconsistencia de avance físico: El avance por registrar ({porcentaje_nuevo}%) "
                    f"no puede ser menor al último avance registrado previamente ({ultimo_avance}%)."
                )
            )
        if porcentaje_nuevo < Decimal("0.00") or porcentaje_nuevo > Decimal("100.00"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El porcentaje de avance físico debe encontrarse en el rango de 0.00% a 100.00%."
            )

    @staticmethod
    def _obra_tiene_ensayos_rechazados(session: Session, id_obra: int) -> bool:
        est_rech = session.exec(
            select(CatEstatus).where(CatEstatus.ambito == "CALIDAD", CatEstatus.clave == "RECHAZADO")
        ).first()
        if not est_rech:
            return False
        prueba = session.exec(
            select(ControlCalidadPruebas)
            .join(ObraConceptos)
            .where(
                ObraConceptos.id_obra == id_obra,
                ControlCalidadPruebas.id_estatus_dictamen == est_rech.id_estatus
            )
        ).first()
        return prueba is not None

    @staticmethod
    def crear_reporte_borrador(
        session: Session,
        reporte_in: models.ReporteDiarioSupervisionCreate,
        supervisor: Usuarios
    ) -> models.ReporteDiarioSupervisionPublic:
        """
        RF-SUP-03 (RN-SUP-03.2, RN-SUP-03.4, RN-SUP-03.6):
        Crea el reporte en estado BORRADOR permitiendo dejar campos incompletos sin enviar.
        """
        obra = session.get(Obras, reporte_in.id_obra)
        if not obra:
            raise HTTPException(status_code=404, detail="Obra no encontrada.")

        est_obra = session.get(CatEstatus, obra.id_estatus)
        if not est_obra or est_obra.clave != "EN_EJECUCION":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"RF-SUP-03: La obra debe estar EN_EJECUCION para crear reportes (estado actual: {est_obra.clave if est_obra else 'DESCONOCIDO'})."
            )

        existente = session.exec(
            select(ReporteDiarioSupervision).where(
                ReporteDiarioSupervision.id_obra == reporte_in.id_obra,
                ReporteDiarioSupervision.fecha_reporte == reporte_in.fecha_reporte
            )
        ).first()
        if existente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"RN-SUP-03.2: Ya existe un reporte de supervisión para la obra en la fecha {reporte_in.fecha_reporte}."
            )

        if reporte_in.porcentaje_avance_reportado is not None:
            SupervisionCalidadService._validar_progresividad_avance(
                session, obra.id_obra, reporte_in.porcentaje_avance_reportado
            )

        id_est_borrador = SupervisionCalidadService._obtener_estatus_reporte_id(session, "BORRADOR")
        nuevo = ReporteDiarioSupervision(
            id_obra=reporte_in.id_obra,
            id_supervisor=supervisor.id_usuario,
            id_estatus_reporte=id_est_borrador,
            fecha_reporte=reporte_in.fecha_reporte,
            actividades_realizadas=reporte_in.actividades_realizadas,
            clima=reporte_in.clima,
            horas_lluvia=(
                reporte_in.horas_lluvia if reporte_in.horas_lluvia is not None else Decimal("0.00")
            ),
            maquinaria_cantidad=reporte_in.maquinaria_cantidad or 0,
            equipo_cantidad=reporte_in.equipo_cantidad or 0,
            personal_cantidad=reporte_in.personal_cantidad or 0,
            porcentaje_avance_reportado=reporte_in.porcentaje_avance_reportado,
            sello_digital=None
        )
        session.add(nuevo)
        session.flush()
        if reporte_in.incidentes:
            SupervisionCalidadService._sincronizar_incidentes(
                session, nuevo.id_reporte, reporte_in.incidentes
            )
        session.commit()
        session.refresh(nuevo)
        return SupervisionCalidadService._enriquecer_reporte(session, nuevo)

    @staticmethod
    def actualizar_reporte(
        session: Session,
        id_reporte: int,
        reporte_in: models.ReporteDiarioSupervisionUpdate
    ) -> models.ReporteDiarioSupervisionPublic:
        """
        RN-SUP-03.4: Permite modificar el reporte tanto en BORRADOR como en ENVIADO,
        siempre y cuando aún NO haya sido firmado electrónicamente (firmado == False).
        """
        reporte = session.get(ReporteDiarioSupervision, id_reporte)
        if not reporte:
            raise HTTPException(status_code=404, detail="Reporte de supervisión no encontrado.")

        est_actual = session.get(CatEstatus, reporte.id_estatus_reporte)
        if est_actual and est_actual.clave == "FIRMADO":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="RN-SUP-03.4 / RNF-SEG-02: El reporte ya fue firmado electrónicamente y es inmutable."
            )

        if reporte_in.porcentaje_avance_reportado is not None:
            SupervisionCalidadService._validar_progresividad_avance(
                session, reporte.id_obra, reporte_in.porcentaje_avance_reportado
            )

        datos = reporte_in.model_dump(exclude_unset=True)
        datos.pop("incidentes", None)
        no_nulos_default = {
            "horas_lluvia": Decimal("0.00"),
            "maquinaria_cantidad": 0,
            "equipo_cantidad": 0,
            "personal_cantidad": 0,
        }
        for campo, valor in datos.items():
            if campo in no_nulos_default and valor is None:
                valor = no_nulos_default[campo]
            setattr(reporte, campo, valor)

        session.add(reporte)
        if reporte_in.incidentes is not None:
            SupervisionCalidadService._sincronizar_incidentes(
                session, reporte.id_reporte, reporte_in.incidentes
            )
        session.commit()
        session.refresh(reporte)
        return SupervisionCalidadService._enriquecer_reporte(session, reporte)

    @staticmethod
    def enviar_reporte(
        session: Session, id_reporte: int
    ) -> models.ReporteDiarioSupervisionPublic:
        """
        RN-SUP-03.4: Valida que todos los campos obligatorios estén completos para pasar
        de BORRADOR a ENVIADO (sigue siendo editable mientras no se firme).
        """
        reporte = session.get(ReporteDiarioSupervision, id_reporte)
        if not reporte:
            raise HTTPException(status_code=404, detail="Reporte de supervisión no encontrado.")

        est_actual = session.get(CatEstatus, reporte.id_estatus_reporte)
        if est_actual and est_actual.clave == "FIRMADO":
            raise HTTPException(
                status_code=400,
                detail="Este reporte ya fue firmado y cerrado."
            )

        faltantes = []
        if not reporte.actividades_realizadas or not reporte.actividades_realizadas.strip():
            faltantes.append("actividades_realizadas")
        if not reporte.clima or not reporte.clima.strip():
            faltantes.append("clima")
        if reporte.porcentaje_avance_reportado is None:
            faltantes.append("porcentaje_avance_reportado")
        if reporte.personal_cantidad is None or reporte.personal_cantidad <= 0:
            faltantes.append("personal_cantidad")

        if faltantes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"RN-SUP-03.4: Para enviar el reporte debe completar los campos obligatorios: {', '.join(faltantes)}."
            )

        if reporte.porcentaje_avance_reportado is not None:
            SupervisionCalidadService._validar_progresividad_avance(
                session, reporte.id_obra, reporte.porcentaje_avance_reportado
            )

        reporte.id_estatus_reporte = SupervisionCalidadService._obtener_estatus_reporte_id(session, "ENVIADO")
        reporte.fecha_envio = datetime.now(timezone.utc)
        session.add(reporte)
        session.commit()
        session.refresh(reporte)
        return SupervisionCalidadService._enriquecer_reporte(session, reporte)

    @staticmethod
    def actualizar_estatus_incidente(
        session: Session,
        id_incidente: int,
        estatus_in: models.ReporteIncidenteEstatusUpdate,
    ) -> models.ReporteIncidentePublic:
        """Actualiza el semáforo del incidente (CREADO -> EMITIDO -> ATENDIDO) y opcionalmente accion_solucion."""
        inc = session.get(ReporteIncidentes, id_incidente)
        if not inc:
            raise HTTPException(status_code=404, detail="Incidente de reporte no encontrado.")

        est_actual = session.get(CatEstatus, inc.id_estatus_incidente)
        clave_actual = est_actual.clave if est_actual else "CREADO"
        nueva_clave = estatus_in.clave_estatus.upper()

        orden_actual = ORDEN_ESTATUS_INCIDENTE.get(clave_actual, 0)
        orden_nuevo = ORDEN_ESTATUS_INCIDENTE.get(nueva_clave, 0)
        if orden_nuevo < orden_actual:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Transición de estatus inválida para el incidente: no se puede retroceder "
                    f"de '{clave_actual}' a '{nueva_clave}' (flujo: CREADO -> EMITIDO -> ATENDIDO)."
                )
            )

        inc.id_estatus_incidente = SupervisionCalidadService._obtener_estatus_incidente_id(
            session, nueva_clave
        )
        if estatus_in.accion_solucion is not None:
            inc.accion_solucion = estatus_in.accion_solucion.strip() or None

        session.add(inc)
        session.commit()
        session.refresh(inc)
        return SupervisionCalidadService._enriquecer_incidente(session, inc)

    @staticmethod
    def firmar_reporte(
        session: Session,
        id_reporte: int,
        firma_in: models.ReporteDiarioFirmaInput,
        supervisor: Usuarios,
        ip_origen: str
    ) -> models.ReporteDiarioSupervisionPublic:
        """
        RN-SUP-03.4, RN-SUP-03.5 y RN-SUP-03.6:
        - Requiere que el reporte esté en estado ENVIADO (completo) y sin firmar.
        - Valida la firma electrónica del Supervisor (RNF-SEG-04) y bloquea el reporte (RNF-SEG-02).
        - Inserta automáticamente el nuevo corte oficial en Avances_Fisicos validando progresividad.
        """
        reporte = session.get(ReporteDiarioSupervision, id_reporte)
        if not reporte:
            raise HTTPException(status_code=404, detail="Reporte de supervisión no encontrado.")

        est_actual = session.get(CatEstatus, reporte.id_estatus_reporte)
        clave_actual = est_actual.clave if est_actual else ""
        if clave_actual == "FIRMADO":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RNF-SEG-02: Este reporte ya cuenta con firma electrónica y es inmutable."
            )

        if clave_actual != "ENVIADO":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RN-SUP-03.4: Debe completar y enviar el reporte (estado ENVIADO) antes de poder firmarlo."
            )

        if reporte.porcentaje_avance_reportado is None:
            raise HTTPException(
                status_code=400,
                detail="El reporte debe incluir 'porcentaje_avance_reportado' antes de firmarse."
            )

        SupervisionCalidadService._validar_progresividad_avance(
            session, reporte.id_obra, reporte.porcentaje_avance_reportado
        )

        sello = validar_firma_electronica_y_generar_sello(
            firma_plana=firma_in.firma_electronica_supervisor,
            firma_hash_usuario=supervisor.firma_electronica,
            id_usuario=supervisor.id_usuario,
            referencia=f"REPORTE-SUP:{reporte.id_reporte}-OBRA:{reporte.id_obra}"
        )

        reporte.id_estatus_reporte = SupervisionCalidadService._obtener_estatus_reporte_id(session, "FIRMADO")
        reporte.sello_digital = sello
        reporte.fecha_firma = datetime.now(timezone.utc)
        session.add(reporte)
        session.commit()
        session.refresh(reporte)

        # RN-SUP-03.5: Interacción automática Reporte de Supervisión -> Avances_Fisicos
        DirectivoFiniquitoService.registrar_corte_avance(
            session=session,
            id_obra=reporte.id_obra,
            porcentaje_fisico_nuevo=reporte.porcentaje_avance_reportado,
            fecha_corte=reporte.fecha_reporte,
            id_reporte=reporte.id_reporte
        )

        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=supervisor.id_usuario,
            id_obra=reporte.id_obra,
            tipo_accion="FIRMA",
            accion_ejecutada=f"FIRMA_REPORTE_SUPERVISION_{reporte.id_reporte}",
            descripcion=f"Firma de reporte de supervisión del {reporte.fecha_reporte} con avance {reporte.porcentaje_avance_reportado}%",
            ip_origen=ip_origen
        )

        advertencia = None
        if SupervisionCalidadService._obra_tiene_ensayos_rechazados(session, reporte.id_obra):
            advertencia = (
                "ADVERTENCIA (RN-SUP-03.3): Esta obra cuenta con ensayos de laboratorio dictaminados como RECHAZADO."
            )

        return SupervisionCalidadService._enriquecer_reporte(session, reporte, advertencia_calidad=advertencia)

    @staticmethod
    def consultar_reportes_diarios(
        session: Session, id_obra: int, skip: int = 0, limit: int = 20
    ) -> List[models.ReporteDiarioSupervisionPublic]:
        limit_seguro = min(max(1, limit), 100)
        reportes = list(
            session.exec(
                select(ReporteDiarioSupervision)
                .where(ReporteDiarioSupervision.id_obra == id_obra)
                .order_by(col(ReporteDiarioSupervision.fecha_reporte).desc())
                .offset(max(0, skip))
                .limit(limit_seguro)
            ).all()
        )
        return [SupervisionCalidadService._enriquecer_reporte(session, r) for r in reportes]

    @staticmethod
    def registrar_prueba_calidad(
        session: Session, prueba_in: models.ControlCalidadPruebaCreate
    ) -> models.ControlCalidadPruebaPublic:
        concepto = session.get(ObraConceptos, prueba_in.id_obra_concepto)
        if not concepto:
            raise HTTPException(status_code=404, detail="Concepto de obra no encontrado.")

        tipo_ensayo = session.get(CatTipoEnsayo, prueba_in.id_tipo_ensayo)
        if not tipo_ensayo or not tipo_ensayo.activo:
            raise HTTPException(status_code=404, detail="Tipo de ensayo de laboratorio no válido.")

        validar_formato_y_tamano_archivo(prueba_in.url_reporte_laboratorio, (".pdf", ".jpg", ".jpeg", ".png"))

        est_dictamen = session.exec(
            select(CatEstatus).where(
                CatEstatus.ambito == "CALIDAD",
                CatEstatus.clave == prueba_in.clave_dictamen.upper()
            )
        ).first()
        if not est_dictamen:
            raise HTTPException(status_code=400, detail="Estatus de dictamen de calidad no válido.")

        nueva = ControlCalidadPruebas(
            id_obra_concepto=prueba_in.id_obra_concepto,
            id_tipo_ensayo=prueba_in.id_tipo_ensayo,
            id_estatus_dictamen=est_dictamen.id_estatus,
            fecha_muestreo=prueba_in.fecha_muestreo,
            valor_obtenido=prueba_in.valor_obtenido,
            url_reporte_laboratorio=prueba_in.url_reporte_laboratorio
        )
        session.add(nueva)
        session.commit()
        session.refresh(nueva)

        return models.ControlCalidadPruebaPublic(
            **nueva.model_dump(),
            clave_dictamen=est_dictamen.clave
        )

    @staticmethod
    def consultar_pruebas_obra(
        session: Session, id_obra: int
    ) -> List[models.ControlCalidadPruebaPublic]:
        pruebas = list(
            session.exec(
                select(ControlCalidadPruebas)
                .join(ObraConceptos)
                .where(ObraConceptos.id_obra == id_obra)
            ).all()
        )
        resultado: List[models.ControlCalidadPruebaPublic] = []
        for p in pruebas:
            est = session.get(CatEstatus, p.id_estatus_dictamen)
            resultado.append(
                models.ControlCalidadPruebaPublic(
                    **p.model_dump(),
                    clave_dictamen=est.clave if est else None
                )
            )
        return resultado
