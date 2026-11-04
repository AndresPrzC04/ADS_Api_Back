from datetime import date, timedelta
from typing import List
from fastapi import HTTPException, status
from sqlmodel import Session, col, func, select
from app.core.security import (
    validar_firma_electronica_y_generar_sello,
    validar_formato_y_tamano_archivo,
)
from app.models_base import (
    BitacoraNotas,
    CatEstatus,
    CatTipoEnsayo,
    CatTipoNotaBitacora,
    ConceptosCatalogo,
    Contratos,
    ControlCalidadPruebas,
    EvidenciaAdjunta,
    Generadores,
    Obras,
    ProgramaEjecucion,
    ReporteDiarioSupervision,
    Usuarios,
)
from app.modules.usuario_accesos.service import AuditoriaService
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
# 1. SERVICIO: BITÁCORA ELECTRÓNICA INMUTABLE Y RECALENDARIZACIÓN (RF-RES-01, RF-RES-02, RF-SUPT-05, RF-SUP-03, RF-SYS-01)
# ==========================================
class BitacoraService:
    @staticmethod
    def _verificar_bitacora_no_cerrada(session: Session, id_obra: int) -> None:
        """
        RN-RES-01.2: Cuando el Residente registra y firma la nota de CIERRE, el backend bloquea
        de forma irreversible cualquier petición POST, PUT, PATCH o DELETE sobre Bitacora_notas
        y Evidencia_adjunta con HTTP 403 Forbidden.
        """
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

        # RN-RES-01.2: Verificar que la bitácora no esté cerrada y congelada
        BitacoraService._verificar_bitacora_no_cerrada(session, obra.id_obra)

        # RN-ADM-04.3: Bloqueo preventivo si la obra está EN_CONFIGURACION o ALERTA_VACANTE_OPERATIVA
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

        # RN-SUPT-05.1, RN-SUP-03.1 y RF-RES-01: Validar tipos de nota permitidos por rol
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

        # RN-RES-01.1: Regla de la Nota #1 - Apertura
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
            # Verificar que la Nota #1 de APERTURA esté firmada antes de permitir notas subsecuentes
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

        # RN-RES-02.1: Habilitación de Cantidades Adicionales por el Residente
        if nota_in.id_concepto_adicional is not None and nota_in.cantidad_adicional_autorizada is not None:
            if rol_nombre != "RESIDENTE":
                raise HTTPException(
                    status_code=403,
                    detail="RN-RES-02.1: Solo el Residente puede autorizar cantidades adicionales en catálogo."
                )
            conc = session.get(ConceptosCatalogo, nota_in.id_concepto_adicional)
            if not conc or conc.id_obra != obra.id_obra:
                raise HTTPException(status_code=404, detail="Concepto para cantidad adicional no encontrado en la obra.")
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
        """
        RNF-SEG-02, RNF-SEG-04, RN-SUPT-05.2, RN-RES-01.2 y RN-RES-02.2 (RF-SYS-01):
        - Valida que el autor de la nota sea quien firma y verifica su firma electrónica.
        - Si es AVISO_TERMINACION, exige mínimo 6 fotografías en Evidencia_adjunta.
        - Si es SUSPENSION_TEMPORAL, pasa la obra a SUSPENDIDA.
        - Si es REANUDACION, calcula Δdías y desplaza automáticamente fechas en Programa_ejecucion y Obras.
        - Si es CIERRE, congela la bitácora y pasa la obra/contrato a CERRADA/FINIQUITADA.
        """
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

        # RN-SUPT-05.2: Regla de las 6 evidencias en Aviso de Terminación
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

        # RN-RES-02.2 / RF-SYS-01: Suspensión temporal y Reanudación con recalendarización automática
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

            # Desplazar fecha_fin_prog pendientes en Programa_ejecucion y fecha_fin en Obras
            actividades = list(
                session.exec(
                    select(ProgramaEjecucion)
                    .join(ConceptosCatalogo)
                    .where(
                        ConceptosCatalogo.id_obra == obra.id_obra,
                        col(ProgramaEjecucion.fecha_fin_prog) >= fecha_susp
                    )
                ).all()
            )
            for act in actividades:
                act.fecha_fin_prog = act.fecha_fin_prog + timedelta(days=delta_dias)
                session.add(act)

            obra.fecha_fin = obra.fecha_fin + timedelta(days=delta_dias)
            est_eje = session.exec(
                select(CatEstatus).where(CatEstatus.ambito == "OBRA", CatEstatus.clave == "EN_EJECUCION")
            ).first()
            if est_eje:
                obra.id_estatus = est_eje.id_estatus
            session.add(obra)

        elif clave_tipo == "CIERRE" and obra:
            # RN-RES-05.2: Al firmar la nota de CIERRE, Obra y Contrato pasan a FINIQUITADA / CERRADA
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
        """RN-DIR-03.2 y RNF-REN-03: Paginación obligatoria en consulta de notas de bitácora."""
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
# 2. SERVICIO: EVIDENCIA FOTOGRÁFICA ADJUNTA (RF-SUPT-04, RF-SUPT-05, RN-SUPT-05.3)
# ==========================================
class EvidenciaService:
    @staticmethod
    def agregar_evidencia(
        session: Session, ev_in: models.EvidenciaAdjuntaCreate
    ) -> EvidenciaAdjunta:
        # Validar origen único (chk_evidencia_origen_unico)
        tiene_nota = ev_in.id_nota is not None
        tiene_gen = ev_in.id_generador is not None
        if tiene_nota == tiene_gen:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debe vincular la evidencia exactamente a una nota de bitácora (id_nota) o a un generador (id_generador), no a ambos."
            )

        # RN-SUPT-04.2 y RNF-USA-05: Validar formato permitido (.pdf, .jpg, .jpeg, .png)
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
        elif ev_in.id_generador is not None:
            gen = session.get(Generadores, ev_in.id_generador)
            if not gen:
                raise HTTPException(status_code=404, detail="Generador no encontrado.")

        nueva_ev = EvidenciaAdjunta(
            id_nota=ev_in.id_nota,
            id_generador=ev_in.id_generador,
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

        session.delete(ev)
        session.commit()
        return {"detalle": f"Evidencia {id_evidencia} eliminada correctamente."}


# ==========================================
# 3. SERVICIO: CONTROL DE CALIDAD Y REPORTE DIARIO DE SUPERVISIÓN (RF-SUP-03)
# ==========================================
class SupervisionCalidadService:
    @staticmethod
    def registrar_prueba_calidad(
        session: Session, prueba_in: models.ControlCalidadPruebaCreate
    ) -> models.ControlCalidadPruebaPublic:
        """RN-SUP-03.3: Registro de ensayos de laboratorio por concepto en 3NF."""
        concepto = session.get(ConceptosCatalogo, prueba_in.id_concepto)
        if not concepto:
            raise HTTPException(status_code=404, detail="Concepto no encontrado.")

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
            id_concepto=prueba_in.id_concepto,
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
                .join(ConceptosCatalogo)
                .where(ConceptosCatalogo.id_obra == id_obra)
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

    @staticmethod
    def crear_reporte_diario(
        session: Session, reporte_in: models.ReporteDiarioSupervisionCreate, supervisor: Usuarios
    ) -> ReporteDiarioSupervision:
        """RN-SUP-03.2: Máximo un reporte diario de supervisión por obra y fecha."""
        obra = session.get(Obras, reporte_in.id_obra)
        if not obra:
            raise HTTPException(status_code=404, detail="Obra no encontrada.")

        existente = session.exec(
            select(ReporteDiarioSupervision).where(
                ReporteDiarioSupervision.id_obra == reporte_in.id_obra,
                ReporteDiarioSupervision.fecha_reporte == reporte_in.fecha_reporte
            )
        ).first()
        if existente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"RN-SUP-03.2: Ya existe un reporte diario de supervisión para la obra en la fecha {reporte_in.fecha_reporte}."
            )

        nuevo = ReporteDiarioSupervision(
            id_obra=reporte_in.id_obra,
            id_supervisor=supervisor.id_usuario,
            fecha_reporte=reporte_in.fecha_reporte,
            clima=reporte_in.clima,
            estado_fuerza_trabajo=reporte_in.estado_fuerza_trabajo,
            maquinaria_activa=reporte_in.maquinaria_activa,
            incidencias_relevantes=reporte_in.incidencias_relevantes
        )
        session.add(nuevo)
        session.commit()
        session.refresh(nuevo)
        return nuevo

    @staticmethod
    def consultar_reportes_diarios(
        session: Session, id_obra: int
    ) -> List[ReporteDiarioSupervision]:
        return list(
            session.exec(
                select(ReporteDiarioSupervision)
                .where(ReporteDiarioSupervision.id_obra == id_obra)
                .order_by(col(ReporteDiarioSupervision.fecha_reporte).desc())
            ).all()
        )
