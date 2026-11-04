from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List
from fastapi import HTTPException, status
from sqlmodel import Session, col, func, or_, select
from app.core.security import (
    validar_firma_electronica_y_generar_sello,
    validar_formato_y_tamano_archivo,
)
from app.models_base import (
    BitacoraNotas,
    CatEstatus,
    CatTipoConcepto,
    CatTipoEstimacion,
    CatTipoNotaBitacora,
    ConceptosCatalogo,
    Contratos,
    ControlCalidadPruebas,
    Estimaciones,
    EstimacionesPagadas,
    EvidenciaAdjunta,
    FacturacionEstimacion,
    Generadores,
    GeneradoresValidacion,
    Obras,
    ObrasAsignaciones,
    ProgramaEjecucion,
    RevisionEstimaciones,
    RolUsuario,
    Usuarios,
)
from app.modules.obras_contratos.service import DirectivoFiniquitoService
from app.modules.usuarios_accesos.service import AuditoriaService
from . import models


def _redondear_2(valor: Decimal) -> Decimal:
    return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ==========================================
# 1. SERVICIO: GESTIÓN DE ESTIMACIONES Y SUBSANACIÓN (RF-SUPT-03, RF-SUPT-07)
# ==========================================
class EstimacionService:
    @staticmethod
    def _obtener_estatus_id(session: Session, ambito: str, clave: str) -> int:
        est = session.exec(
            select(CatEstatus).where(CatEstatus.ambito == ambito, CatEstatus.clave == clave)
        ).first()
        if not est:
            raise HTTPException(
                status_code=500,
                detail=f"Estatus institucional ({ambito}: {clave}) no encontrado en Cat_Estatus."
            )
        return est.id_estatus

    @staticmethod
    def _enriquecer_estimacion(session: Session, est: Estimaciones) -> models.EstimacionPublic:
        cat_est = session.get(CatEstatus, est.id_estatus)
        cat_tipo = session.get(CatTipoEstimacion, est.id_tipo_estimacion)
        return models.EstimacionPublic(
            id_estimacion=est.id_estimacion,
            id_obra=est.id_obra,
            id_superintendente=est.id_superintendente,
            id_tipo_estimacion=est.id_tipo_estimacion,
            clave_tipo_estimacion=cat_tipo.clave if cat_tipo else None,
            id_estatus=est.id_estatus,
            clave_estatus=cat_est.clave if cat_est else None,
            numero_estimacion=est.numero_estimacion,
            version_subsanacion=est.version_subsanacion,
            periodo_inicio=est.periodo_inicio,
            periodo_fin=est.periodo_fin,
            fecha_presentacion=est.fecha_presentacion,
            monto_bruto=est.monto_bruto,
            monto_amortizacion=est.monto_amortizacion,
            monto_neto=est.monto_neto
        )

    @staticmethod
    def recalcular_montos(session: Session, estimacion: Estimaciones) -> None:
        """
        RN-SUPT-03.5: El sistema calcula automáticamente:
        monto_bruto = Σ(cant_ejecutada * precio_unitario)
        monto_neto = monto_bruto - monto_amortizacion
        """
        generadores = list(
            session.exec(
                select(Generadores).where(Generadores.id_estimacion == estimacion.id_estimacion)
            ).all()
        )

        total_bruto = Decimal("0.00")
        for gen in generadores:
            concepto = session.get(ConceptosCatalogo, gen.id_concepto)
            if concepto:
                total_bruto += _redondear_2(gen.cant_ejecutada * concepto.precio_unitario)

        estimacion.monto_bruto = _redondear_2(total_bruto)
        estimacion.monto_neto = max(Decimal("0.00"), _redondear_2(total_bruto - estimacion.monto_amortizacion))
        session.add(estimacion)
        session.commit()
        session.refresh(estimacion)

    @staticmethod
    def crear_borrador(
        session: Session,
        estimacion_in: models.EstimacionCreate,
        superintendente: Usuarios,
        ip_origen: str
    ) -> models.EstimacionPublic:
        obra = session.get(Obras, estimacion_in.id_obra)
        if not obra:
            raise HTTPException(status_code=404, detail="La obra especificada no existe.")

        # RN-ADM-04.3 y Precondiciones RF-SUPT-03: La obra debe estar EN_EJECUCION
        est_obra = session.get(CatEstatus, obra.id_estatus)
        if not est_obra or est_obra.clave != "EN_EJECUCION":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"RN-ADM-04.3 / RF-SUPT-03: No se pueden registrar estimaciones mientras la obra "
                    f"se encuentre en estado '{est_obra.clave if est_obra else 'DESCONOCIDO'}'. Debe estar EN_EJECUCION."
                )
            )

        # Precondición RF-SUPT-03: Debe existir Nota de Apertura firmada en Bitácora
        tipo_apertura = session.exec(
            select(CatTipoNotaBitacora).where(CatTipoNotaBitacora.clave == "APERTURA")
        ).first()
        nota_apertura = None
        if tipo_apertura:
            nota_apertura = session.exec(
                select(BitacoraNotas).where(
                    BitacoraNotas.id_obra == obra.id_obra,
                    BitacoraNotas.id_tipo_nota == tipo_apertura.id_tipo_nota,
                    col(BitacoraNotas.firmada).is_(True)
                )
            ).first()
        if not nota_apertura:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RF-SUPT-03: Precondición incumplida. La obra requiere Nota de Apertura firmada por el Residente."
            )

        # Precondición RF-SUPT-03: Debe tener cargado Catálogo de Conceptos y Programa de Ejecución
        tiene_catalogo = session.exec(
            select(ConceptosCatalogo).where(ConceptosCatalogo.id_obra == obra.id_obra)
        ).first()
        tiene_programa = session.exec(
            select(ProgramaEjecucion)
            .join(ConceptosCatalogo)
            .where(ConceptosCatalogo.id_obra == obra.id_obra)
        ).first()
        if not tiene_catalogo or not tiene_programa:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RF-SUPT-03: La obra debe contar con Catálogo de Conceptos y Programa de Ejecución cargados."
            )

        if estimacion_in.periodo_fin < estimacion_in.periodo_inicio:
            raise HTTPException(status_code=400, detail="La fecha fin del periodo no puede ser menor a la de inicio.")

        tipo_est = session.get(CatTipoEstimacion, estimacion_in.id_tipo_estimacion)
        if not tipo_est or not tipo_est.activo:
            raise HTTPException(status_code=404, detail="Tipo de estimación no encontrado o inactivo.")

        # RN-SUPT-03.4: Secuencia de número de estimación y no traslape de periodos en ordinarias
        duplicado_num = session.exec(
            select(Estimaciones).where(
                Estimaciones.id_obra == obra.id_obra,
                Estimaciones.numero_estimacion == estimacion_in.numero_estimacion
            )
        ).first()
        if duplicado_num:
            raise HTTPException(
                status_code=400,
                detail=f"RN-SUPT-03.4: Ya existe la estimación #{estimacion_in.numero_estimacion} en esta obra."
            )

        if tipo_est.clave == "ORDINARIA":
            ordinarias_previas = list(
                session.exec(
                    select(Estimaciones).where(
                        Estimaciones.id_obra == obra.id_obra,
                        Estimaciones.id_tipo_estimacion == tipo_est.id_tipo_estimacion
                    )
                ).all()
            )
            for prev in ordinarias_previas:
                if (
                    estimacion_in.periodo_inicio <= prev.periodo_fin
                    and estimacion_in.periodo_fin >= prev.periodo_inicio
                ):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"RN-SUPT-03.4: El periodo ({estimacion_in.periodo_inicio} a {estimacion_in.periodo_fin}) "
                            f"se traslapa con la estimación ordinaria #{prev.numero_estimacion} "
                            f"({prev.periodo_inicio} a {prev.periodo_fin})."
                        )
                    )

        id_borrador = EstimacionService._obtener_estatus_id(session, "ESTIMACION", "BORRADOR")
        nueva = Estimaciones(
            id_obra=obra.id_obra,
            id_superintendente=superintendente.id_usuario,
            id_tipo_estimacion=estimacion_in.id_tipo_estimacion,
            id_estatus=id_borrador,
            numero_estimacion=estimacion_in.numero_estimacion,
            version_subsanacion=1,
            periodo_inicio=estimacion_in.periodo_inicio,
            periodo_fin=estimacion_in.periodo_fin,
            fecha_presentacion=date.today(),
            monto_bruto=Decimal("0.00"),
            monto_amortizacion=estimacion_in.monto_amortizacion,
            monto_neto=Decimal("0.00")
        )
        session.add(nueva)
        session.commit()
        session.refresh(nueva)

        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=superintendente.id_usuario,
            id_obra=obra.id_obra,
            tipo_accion="CREACION",
            accion_ejecutada=f"CREACION_ESTIMACION_{nueva.id_estimacion}",
            descripcion=f"Borrador de estimación #{nueva.numero_estimacion} ({tipo_est.clave})",
            ip_origen=ip_origen
        )
        return EstimacionService._enriquecer_estimacion(session, nueva)

    @staticmethod
    def obtener_por_id(session: Session, id_estimacion: int) -> Estimaciones:
        est = session.get(Estimaciones, id_estimacion)
        if not est:
            raise HTTPException(status_code=404, detail="Estimación no encontrada.")
        return est

    @staticmethod
    def obtener_detalle_public(session: Session, id_estimacion: int) -> models.EstimacionPublicDetalle:
        est = EstimacionService.obtener_por_id(session, id_estimacion)
        base = EstimacionService._enriquecer_estimacion(session, est)
        generadores = GeneradorService.consultar_por_estimacion(session, id_estimacion)
        revisiones = RevisionEstimacionService.consultar_por_estimacion(session, id_estimacion)
        factura = session.exec(
            select(FacturacionEstimacion).where(FacturacionEstimacion.id_estimacion == id_estimacion)
        ).first()
        pago = session.get(EstimacionesPagadas, id_estimacion)

        return models.EstimacionPublicDetalle(
            **base.model_dump(),
            generadores=generadores,
            revisiones=revisiones,
            facturacion=models.FacturacionEstimacionPublic(**factura.model_dump()) if factura else None,
            pago=models.EstimacionPagadaPublic(**pago.model_dump()) if pago else None
        )

    @staticmethod
    def consultar_por_obra(session: Session, id_obra: int) -> List[models.EstimacionPublic]:
        lista = list(
            session.exec(
                select(Estimaciones)
                .where(Estimaciones.id_obra == id_obra)
                .order_by(col(Estimaciones.numero_estimacion).asc())
            ).all()
        )
        return [EstimacionService._enriquecer_estimacion(session, e) for e in lista]

    @staticmethod
    def eliminar_borrador(session: Session, id_estimacion: int) -> dict:
        est = EstimacionService.obtener_por_id(session, id_estimacion)
        cat_est = session.get(CatEstatus, est.id_estatus)
        if not cat_est or cat_est.clave != "BORRADOR":
            raise HTTPException(
                status_code=400,
                detail="RNF-SEG-02: Solo se pueden eliminar estimaciones en estado BORRADOR."
            )
        session.delete(est)
        session.commit()
        return {"detalle": f"Estimación {id_estimacion} en borrador eliminada correctamente."}

    @staticmethod
    def enviar_a_revision(
        session: Session, id_estimacion: int, superintendente: Usuarios, ip_origen: str
    ) -> models.EstimacionPublic:
        """
        RN-SUPT-04.1, RN-SUPT-07.2 y RN-SUP-06.1: Valida que existan generadores y que TODOS
        tengan croquis_url y al menos 1 fotografía en Evidencia_adjunta. Si proviene de RECHAZADA,
        incrementa version_subsanacion y crea un nuevo registro en Revision_Estimaciones con
        fecha_recepcion = hoy para iniciar el reloj normativo de 15 días.
        """
        est = EstimacionService.obtener_por_id(session, id_estimacion)
        cat_est = session.get(CatEstatus, est.id_estatus)
        clave_actual = cat_est.clave if cat_est else ""

        if clave_actual not in {"BORRADOR", "RECHAZADA", "OBSERVADA"}:
            raise HTTPException(
                status_code=400,
                detail=f"La estimación en estado '{clave_actual}' no puede enviarse a revisión."
            )

        generadores = list(
            session.exec(
                select(Generadores).where(Generadores.id_estimacion == id_estimacion)
            ).all()
        )
        if not generadores:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RN-SUPT-04.1: Una estimación no puede pasar a EN_REVISION sin al menos un registro en Generadores."
            )

        for gen in generadores:
            if not gen.croquis_url or not gen.croquis_url.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"RN-SUPT-04.1: El generador ID {gen.id_generador} carece de archivo de croquis (croquis_url vacío)."
                )
            num_fotos = session.exec(
                select(func.count(col(EvidenciaAdjunta.id_evidencia))).where(
                    EvidenciaAdjunta.id_generador == gen.id_generador
                )
            ).one()
            if num_fotos < 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"RN-SUPT-04.1: El generador ID {gen.id_generador} requiere al menos 1 fotografía en Evidencia_adjunta."
                )

        # Si viene de rechazo, incrementar versión de subsanación (RN-SUPT-07.1 y RN-SUPT-07.2)
        if clave_actual in {"RECHAZADA", "OBSERVADA"}:
            est.version_subsanacion += 1

        EstimacionService.recalcular_montos(session, est)
        est.id_estatus = EstimacionService._obtener_estatus_id(session, "ESTIMACION", "EN_REVISION")
        est.fecha_presentacion = date.today()
        session.add(est)

        # RN-SUP-06.1: Estampar automáticamente fecha_recepcion en Revision_Estimaciones
        hoy = date.today()
        asig_sup = session.exec(
            select(ObrasAsignaciones)
            .join(Usuarios)
            .join(RolUsuario)
            .where(
                ObrasAsignaciones.id_obra == est.id_obra,
                RolUsuario.nombre == "SUPERVISOR",
                col(ObrasAsignaciones.fecha_inicio_asignacion) <= hoy,
                or_(
                    col(ObrasAsignaciones.fecha_fin_asignacion).is_(None),
                    col(ObrasAsignaciones.fecha_fin_asignacion) >= hoy,
                ),
            )
        ).first()
        id_sup_obra = asig_sup.id_usuario if asig_sup else superintendente.id_usuario
        id_est_pend = EstimacionService._obtener_estatus_id(session, "REVISION", "PENDIENTE")

        rev_existente = session.exec(
            select(RevisionEstimaciones).where(
                RevisionEstimaciones.id_estimacion == est.id_estimacion,
                RevisionEstimaciones.version_revisada == est.version_subsanacion
            )
        ).first()
        if not rev_existente:
            nueva_rev = RevisionEstimaciones(
                id_estimacion=est.id_estimacion,
                id_supervisor=id_sup_obra,
                id_estatus_revision=id_est_pend,
                version_revisada=est.version_subsanacion,
                fecha_recepcion=hoy,
                fecha_autorizacion=None,
                monto_autorizado_neto=Decimal("0.00")
            )
            session.add(nueva_rev)

        session.commit()
        session.refresh(est)

        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=superintendente.id_usuario,
            id_obra=est.id_obra,
            tipo_accion="ENVIO_REVISION",
            accion_ejecutada=f"ENVIO_ESTIMACION_{est.id_estimacion}_V{est.version_subsanacion}",
            descripcion=f"Envío a revisión de estimación #{est.numero_estimacion} versión {est.version_subsanacion}",
            ip_origen=ip_origen
        )
        return EstimacionService._enriquecer_estimacion(session, est)


# ==========================================
# 2. SERVICIO: NÚMEROS GENERADORES Y VALIDACIÓN TÉCNICA (RF-SUPT-04, RF-SUP-01)
# ==========================================
class GeneradorService:
    @staticmethod
    def _tiene_ensayo_rechazado(session: Session, id_concepto: int) -> bool:
        """RN-SUP-03.3: Verifica si el concepto tiene algún ensayo de laboratorio con dictamen RECHAZADO."""
        est_rech = session.exec(
            select(CatEstatus).where(CatEstatus.ambito == "CALIDAD", CatEstatus.clave == "RECHAZADO")
        ).first()
        if not est_rech:
            return False
        prueba = session.exec(
            select(ControlCalidadPruebas).where(
                ControlCalidadPruebas.id_concepto == id_concepto,
                ControlCalidadPruebas.id_estatus_dictamen == est_rech.id_estatus
            )
        ).first()
        return prueba is not None

    @staticmethod
    def _validar_tipo_y_tope_volumen(
        session: Session,
        estimacion: Estimaciones,
        concepto: ConceptosCatalogo,
        cant_nueva: Decimal,
        id_generador_excluir: int = 0
    ) -> None:
        """
        RN-SUPT-03.1, RN-SUPT-03.2, RN-SUPT-03.3 y RN-SUPT-03.6:
        Verifica que el concepto corresponda al tipo de estimación y no rebase el volumen autorizado.
        """
        if concepto.id_obra != estimacion.id_obra:
            raise HTTPException(status_code=400, detail="El concepto no pertenece a la obra de la estimación.")

        tipo_est = session.get(CatTipoEstimacion, estimacion.id_tipo_estimacion)
        tipo_conc = session.get(CatTipoConcepto, concepto.id_tipo_concepto)
        clave_est = tipo_est.clave if tipo_est else "ORDINARIA"
        clave_conc = tipo_conc.clave if tipo_conc else "ORDINARIO"

        generadores_hist = list(
            session.exec(
                select(Generadores).where(
                    Generadores.id_concepto == concepto.id_concepto,
                    col(Generadores.id_generador) != id_generador_excluir
                )
            ).all()
        )
        volumen_previo = sum((g.cant_ejecutada for g in generadores_hist), Decimal("0.00"))
        volumen_total = volumen_previo + cant_nueva

        if clave_est == "ORDINARIA":
            if clave_conc != "ORDINARIO":
                raise HTTPException(
                    status_code=400,
                    detail="RN-SUPT-03.1: Una estimación ORDINARIA solo puede cobrar conceptos de tipo ORDINARIO."
                )
            if volumen_total > concepto.cantidad_presupuestada:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"RN-SUPT-03.6: El volumen acumulado ({volumen_total}) supera la cantidad presupuestada "
                        f"original ({concepto.cantidad_presupuestada}). Debe tramitarse como CANTIDADES_ADICIONALES."
                    )
                )
        elif clave_est == "CANTIDADES_ADICIONALES":
            if clave_conc != "ORDINARIO":
                raise HTTPException(
                    status_code=400,
                    detail="RN-SUPT-03.2: Las Cantidades Adicionales solo aplican sobre conceptos del catálogo original."
                )
            if concepto.cantidad_adicional_autorizada <= Decimal("0.00"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "RN-SUPT-03.2: El Residente no ha autorizado volumen adicional "
                        "(cantidad_adicional_autorizada = 0) en bitácora para este concepto."
                    )
                )
            tope_adicional = concepto.cantidad_presupuestada + concepto.cantidad_adicional_autorizada
            if volumen_total > tope_adicional:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"RN-SUPT-03.2: El volumen acumulado ({volumen_total}) excede la suma del presupuesto original "
                        f"más la cantidad adicional autorizada ({tope_adicional})."
                    )
                )
        elif clave_est == "EXTRAORDINARIA":
            if clave_conc != "EXTRAORDINARIO" or not concepto.autorizado_por_residente:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "RN-SUPT-03.3: Una estimación EXTRAORDINARIA solo puede cobrar conceptos de tipo "
                        "EXTRAORDINARIO previamente autorizados con APU por el Residente."
                    )
                )
            if volumen_total > concepto.cantidad_presupuestada:
                raise HTTPException(
                    status_code=400,
                    detail=f"El volumen extraordinario ({volumen_total}) excede el autorizado en el APU ({concepto.cantidad_presupuestada})."
                )

    @staticmethod
    def crear(session: Session, gen_in: models.GeneradorCreate) -> models.GeneradorPublic:
        estimacion = EstimacionService.obtener_por_id(session, gen_in.id_estimacion)
        obra = session.get(Obras, estimacion.id_obra)
        est_obra = session.get(CatEstatus, obra.id_estatus) if obra else None
        if est_obra and est_obra.clave == "SUSPENDIDA":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RN-RES-02.2: La obra se encuentra SUSPENDIDA; está bloqueado el registro de generadores."
            )

        cat_est = session.get(CatEstatus, estimacion.id_estatus)
        if not cat_est or cat_est.clave not in {"BORRADOR", "RECHAZADA", "OBSERVADA"}:
            raise HTTPException(
                status_code=400,
                detail="RNF-SEG-02: No se pueden agregar generadores a una estimación en revisión o autorizada."
            )

        if gen_in.croquis_url:
            validar_formato_y_tamano_archivo(gen_in.croquis_url, (".pdf", ".jpg", ".jpeg", ".png"))

        concepto = session.get(ConceptosCatalogo, gen_in.id_concepto)
        if not concepto:
            raise HTTPException(status_code=404, detail="Concepto de catálogo no encontrado.")

        GeneradorService._validar_tipo_y_tope_volumen(
            session, estimacion, concepto, gen_in.cant_ejecutada
        )

        duplicado_tramo = session.exec(
            select(Generadores).where(
                Generadores.id_estimacion == gen_in.id_estimacion,
                Generadores.id_concepto == gen_in.id_concepto,
                Generadores.ubicacion_tramo == gen_in.ubicacion_tramo
            )
        ).first()
        if duplicado_tramo:
            raise HTTPException(
                status_code=400,
                detail="Ya existe un generador para este concepto y tramo en la misma estimación."
            )

        nuevo = Generadores(
            id_estimacion=gen_in.id_estimacion,
            id_concepto=gen_in.id_concepto,
            ubicacion_tramo=gen_in.ubicacion_tramo,
            cant_ejecutada=gen_in.cant_ejecutada,
            croquis_url=gen_in.croquis_url,
            observaciones=gen_in.observaciones
        )
        session.add(nuevo)
        session.commit()
        session.refresh(nuevo)

        EstimacionService.recalcular_montos(session, estimacion)
        return models.GeneradorPublic(
            **nuevo.model_dump(),
            tiene_ensayo_rechazado=GeneradorService._tiene_ensayo_rechazado(session, nuevo.id_concepto)
        )

    @staticmethod
    def consultar_por_estimacion(session: Session, id_estimacion: int) -> List[models.GeneradorPublic]:
        lista = list(
            session.exec(
                select(Generadores).where(Generadores.id_estimacion == id_estimacion)
            ).all()
        )
        return [
            models.GeneradorPublic(
                **g.model_dump(),
                tiene_ensayo_rechazado=GeneradorService._tiene_ensayo_rechazado(session, g.id_concepto)
            )
            for g in lista
        ]

    @staticmethod
    def corregir_generador(
        session: Session, id_generador: int, gen_in: models.GeneradorUpdate
    ) -> models.GeneradorPublic:
        gen = session.get(Generadores, id_generador)
        if not gen:
            raise HTTPException(status_code=404, detail="Generador no encontrado.")

        estimacion = EstimacionService.obtener_por_id(session, gen.id_estimacion)
        cat_est = session.get(CatEstatus, estimacion.id_estatus)
        if not cat_est or cat_est.clave not in {"BORRADOR", "RECHAZADA", "OBSERVADA"}:
            raise HTTPException(
                status_code=400,
                detail="RN-SUPT-07.1 / RNF-SEG-02: Solo se pueden editar generadores cuando la estimación está en BORRADOR o RECHAZADA."
            )

        if gen_in.croquis_url:
            validar_formato_y_tamano_archivo(gen_in.croquis_url, (".pdf", ".jpg", ".jpeg", ".png"))

        concepto = session.get(ConceptosCatalogo, gen.id_concepto)
        if not concepto:
            raise HTTPException(status_code=404, detail="Concepto no encontrado.")
        nueva_cant = gen_in.cant_ejecutada if gen_in.cant_ejecutada is not None else gen.cant_ejecutada
        GeneradorService._validar_tipo_y_tope_volumen(
            session, estimacion, concepto, nueva_cant, id_generador_excluir=gen.id_generador
        )

        datos = gen_in.model_dump(exclude_unset=True)
        for campo, valor in datos.items():
            setattr(gen, campo, valor)

        session.add(gen)
        session.commit()
        session.refresh(gen)

        EstimacionService.recalcular_montos(session, estimacion)
        return models.GeneradorPublic(
            **gen.model_dump(),
            tiene_ensayo_rechazado=GeneradorService._tiene_ensayo_rechazado(session, gen.id_concepto)
        )

    @staticmethod
    def validar_generador(
        session: Session, val_in: models.GeneradorValidacionCreate
    ) -> models.GeneradorValidacionPublic:
        """
        RF-SUP-01 (RN-SUP-01.1 a RN-SUP-01.3) y RN-SUP-03.3:
        - Precondición: La estimación debe estar EN_REVISION.
        - 0 <= cant_aprobada <= cant_ejecutada.
        - Si cant_aprobada < cant_ejecutada, observaciones_auditoria es obligatorio.
        - Guarda la versión revisada sin sobrescribir versiones previas.
        """
        gen = session.get(Generadores, val_in.id_generador)
        if not gen:
            raise HTTPException(status_code=404, detail="Generador no encontrado.")

        estimacion = EstimacionService.obtener_por_id(session, gen.id_estimacion)
        cat_est = session.get(CatEstatus, estimacion.id_estatus)
        if not cat_est or cat_est.clave != "EN_REVISION":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RF-SUP-01: La estimación debe encontrarse en estado EN_REVISION para validar sus generadores."
            )

        # RN-SUP-01.1: Tope de cantidad aprobada
        if val_in.cant_aprobada > gen.cant_ejecutada:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"RN-SUP-01.1: El Supervisor no puede aprobar un volumen ({val_in.cant_aprobada}) "
                    f"mayor al declarado como ejecutado por el contratista ({gen.cant_ejecutada})."
                )
            )

        # RN-SUP-01.2: Justificación obligatoria de recorte o rechazo
        if val_in.cant_aprobada < gen.cant_ejecutada:
            if not val_in.observaciones_auditoria or not val_in.observaciones_auditoria.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "RN-SUP-01.2: Cuando la cantidad aprobada es menor a la ejecutada, "
                        "el campo 'observaciones_auditoria' es obligatorio."
                    )
                )

        # RN-SUP-01.3: Trazabilidad por versión (version_subsanacion actual)
        existente_version = session.exec(
            select(GeneradoresValidacion).where(
                GeneradoresValidacion.id_generador == gen.id_generador,
                GeneradoresValidacion.version_revisada == estimacion.version_subsanacion
            )
        ).first()
        if existente_version:
            existente_version.cant_aprobada = val_in.cant_aprobada
            existente_version.observaciones_auditoria = val_in.observaciones_auditoria
            session.add(existente_version)
            session.commit()
            session.refresh(existente_version)
            registro = existente_version
        else:
            registro = GeneradoresValidacion(
                id_generador=gen.id_generador,
                version_revisada=estimacion.version_subsanacion,
                cant_aprobada=val_in.cant_aprobada,
                observaciones_auditoria=val_in.observaciones_auditoria
            )
            session.add(registro)
            session.commit()
            session.refresh(registro)

        advertencia = None
        if GeneradorService._tiene_ensayo_rechazado(session, gen.id_concepto):
            advertencia = (
                "ADVERTENCIA (RN-SUP-03.3): Este concepto cuenta con al menos una prueba de laboratorio "
                "dictaminada como RECHAZADO en Control_Calidad_Pruebas."
            )

        return models.GeneradorValidacionPublic(
            **registro.model_dump(),
            advertencia_calidad=advertencia
        )


# ==========================================
# 3. SERVICIO: REVISIÓN TÉCNICA, CANDADO FINANCIERO Y AUTORIZACIÓN DE PAGO (RF-SUP-02, RF-SUP-06, RF-RES-03)
# ==========================================
class RevisionEstimacionService:
    @staticmethod
    def dictaminar_estimacion(
        session: Session,
        id_estimacion: int,
        dictamen_in: models.DictamenRevisionInput,
        supervisor: Usuarios,
        ip_origen: str
    ) -> models.RevisionEstimacionPublic:
        """
        RF-SUP-02 (RN-SUP-02.1 a RN-SUP-02.4), RF-SUP-05 y RN-DIR-01.6:
        - Exige firma electrónica del Supervisor.
        - Verifica que el 100% de los generadores tengan validación en la versión actual.
        - Si APROBADA: recalcula monto_autorizado_neto, verifica candado Físico >= Financiero y actualiza Avances_Fisicos.
        - Si RECHAZADA: exige observaciones_rechazo y desbloquea la estimación para subsanación (RF-SUPT-07).
        """
        estimacion = EstimacionService.obtener_por_id(session, id_estimacion)
        cat_est = session.get(CatEstatus, estimacion.id_estatus)
        if not cat_est or cat_est.clave != "EN_REVISION":
            raise HTTPException(
                status_code=400,
                detail="La estimación debe estar en estado EN_REVISION para emitir dictamen."
            )

        # RN-SUP-02.4: Firma electrónica obligatoria del Supervisor
        sello = validar_firma_electronica_y_generar_sello(
            firma_plana=dictamen_in.firma_electronica_supervisor,
            firma_hash_usuario=supervisor.firma_electronica,
            id_usuario=supervisor.id_usuario,
            referencia=f"REVISION-EST:{id_estimacion}-V{estimacion.version_subsanacion}"
        )

        # Precondición RF-SUP-02: El 100% de los generadores deben tener dictamen en la versión actual
        generadores = list(
            session.exec(
                select(Generadores).where(Generadores.id_estimacion == id_estimacion)
            ).all()
        )
        if not generadores:
            raise HTTPException(status_code=400, detail="La estimación no tiene generadores registrados.")

        importe_aprobado_bruto = Decimal("0.00")
        for gen in generadores:
            val = session.exec(
                select(GeneradoresValidacion).where(
                    GeneradoresValidacion.id_generador == gen.id_generador,
                    GeneradoresValidacion.version_revisada == estimacion.version_subsanacion
                )
            ).first()
            if not val:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"RF-SUP-02: Precondición incumplida. El generador ID {gen.id_generador} aún no cuenta "
                        f"con dictamen en Generadores_Validacion para la versión {estimacion.version_subsanacion}."
                    )
                )
            conc = session.get(ConceptosCatalogo, gen.id_concepto)
            if conc:
                importe_aprobado_bruto += _redondear_2(val.cant_aprobada * conc.precio_unitario)

        revision = session.exec(
            select(RevisionEstimaciones).where(
                RevisionEstimaciones.id_estimacion == id_estimacion,
                RevisionEstimaciones.version_revisada == estimacion.version_subsanacion
            )
        ).first()
        if not revision:
            id_pend = EstimacionService._obtener_estatus_id(session, "REVISION", "PENDIENTE")
            revision = RevisionEstimaciones(
                id_estimacion=id_estimacion,
                id_supervisor=supervisor.id_usuario,
                id_estatus_revision=id_pend,
                version_revisada=estimacion.version_subsanacion,
                fecha_recepcion=estimacion.fecha_presentacion
            )

        if dictamen_in.estatus_dictamen == "RECHAZADA":
            # RN-SUP-02.3: Flujo de rechazo y subsanación
            if not dictamen_in.observaciones_rechazo or not dictamen_in.observaciones_rechazo.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="RN-SUP-02.3: Es obligatorio capturar el motivo detallado en 'observaciones_rechazo'."
                )
            revision.id_supervisor = supervisor.id_usuario
            revision.id_estatus_revision = EstimacionService._obtener_estatus_id(session, "REVISION", "RECHAZADA")
            revision.fecha_autorizacion = date.today()
            revision.observaciones_rechazo = dictamen_in.observaciones_rechazo
            revision.monto_autorizado_neto = Decimal("0.00")
            revision.sello_firma_supervisor = sello

            estimacion.id_estatus = EstimacionService._obtener_estatus_id(session, "ESTIMACION", "RECHAZADA")
            session.add(revision)
            session.add(estimacion)
            session.commit()
            session.refresh(revision)

            AuditoriaService.registrar_evento(
                session=session,
                id_usuario=supervisor.id_usuario,
                id_obra=estimacion.id_obra,
                tipo_accion="RECHAZO",
                accion_ejecutada=f"RECHAZO_ESTIMACION_{id_estimacion}_V{estimacion.version_subsanacion}",
                descripcion=f"Rechazo técnico de estimación #{estimacion.numero_estimacion}: {dictamen_in.observaciones_rechazo}",
                ip_origen=ip_origen
            )
            return models.RevisionEstimacionPublic(
                **revision.model_dump(),
                clave_estatus_revision="RECHAZADA"
            )

        # Caso APROBADA (RN-SUP-02.1, RN-SUP-02.2, RF-SUP-05)
        monto_aut_neto = max(
            Decimal("0.00"),
            _redondear_2(importe_aprobado_bruto - estimacion.monto_amortizacion - dictamen_in.retencion_economica_atraso)
        )

        # RN-DIR-01.6 y RN-SUP-02.2: Candado Avance Financiero Real <= Avance Físico Real
        obra = session.get(Obras, estimacion.id_obra)
        if not obra:
            raise HTTPException(status_code=404, detail="Obra no encontrada.")
        metricas_previas = DirectivoFiniquitoService.calcular_avances_obra(session, obra)
        id_rev_aprob = EstimacionService._obtener_estatus_id(session, "REVISION", "APROBADA")
        revs_aprob_previas = list(
            session.exec(
                select(RevisionEstimaciones)
                .join(Estimaciones)
                .where(
                    Estimaciones.id_obra == obra.id_obra,
                    RevisionEstimaciones.id_estatus_revision == id_rev_aprob,
                    col(RevisionEstimaciones.id_estimacion) != id_estimacion
                )
            ).all()
        )
        acumulado_financiero = sum((r.monto_autorizado_neto for r in revs_aprob_previas), Decimal("0.00")) + monto_aut_neto
        nuevo_pct_fin = _redondear_2((acumulado_financiero / obra.presupuesto_total) * Decimal("100.00"))

        if nuevo_pct_fin > metricas_previas["pct_fisico_real"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Violación de control presupuestal: El avance financiero no puede superar al avance físico real ejecutado"
            )

        revision.id_supervisor = supervisor.id_usuario
        revision.id_estatus_revision = id_rev_aprob
        revision.fecha_autorizacion = date.today()
        revision.monto_autorizado_neto = monto_aut_neto
        revision.sello_firma_supervisor = sello

        estimacion.id_estatus = EstimacionService._obtener_estatus_id(session, "ESTIMACION", "APROBADA")
        estimacion.monto_neto = monto_aut_neto

        session.add(revision)
        session.add(estimacion)
        session.commit()
        session.refresh(revision)

        # RN-SUP-02.4: Al aprobarse, se actualiza un nuevo corte en la tabla Avances_Fisicos
        DirectivoFiniquitoService.registrar_corte_avance(session, obra.id_obra, date.today())

        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=supervisor.id_usuario,
            id_obra=estimacion.id_obra,
            tipo_accion="FIRMA",
            accion_ejecutada=f"APROBACION_ESTIMACION_{id_estimacion}_V{estimacion.version_subsanacion}",
            descripcion=f"Aprobación técnica de estimación #{estimacion.numero_estimacion} por ${monto_aut_neto:,.2f}",
            ip_origen=ip_origen
        )

        return models.RevisionEstimacionPublic(
            **revision.model_dump(),
            clave_estatus_revision="APROBADA"
        )

    @staticmethod
    def consultar_por_estimacion(session: Session, id_estimacion: int) -> List[models.RevisionEstimacionPublic]:
        revs = list(
            session.exec(
                select(RevisionEstimaciones)
                .where(RevisionEstimaciones.id_estimacion == id_estimacion)
                .order_by(col(RevisionEstimaciones.version_revisada).asc())
            ).all()
        )
        resultado: List[models.RevisionEstimacionPublic] = []
        for r in revs:
            est = session.get(CatEstatus, r.id_estatus_revision)
            resultado.append(
                models.RevisionEstimacionPublic(
                    **r.model_dump(),
                    clave_estatus_revision=est.clave if est else None
                )
            )
        return resultado

    @staticmethod
    def consultar_alertas_plazo_15_dias(
        session: Session, id_obra: int
    ) -> List[models.AlertaPlazoRevisionPublic]:
        """
        RF-SUP-06 (RN-SUP-06.1 y RN-SUP-06.2): Evalúa el reloj normativo de 15 días naturales
        para todas las revisiones en estado PENDIENTE.
        """
        hoy = date.today()
        id_pend = EstimacionService._obtener_estatus_id(session, "REVISION", "PENDIENTE")
        pendientes = list(
            session.exec(
                select(RevisionEstimaciones)
                .join(Estimaciones)
                .where(
                    Estimaciones.id_obra == id_obra,
                    RevisionEstimaciones.id_estatus_revision == id_pend,
                    col(RevisionEstimaciones.fecha_autorizacion).is_(None)
                )
            ).all()
        )

        alertas: List[models.AlertaPlazoRevisionPublic] = []
        for r in pendientes:
            est = session.get(Estimaciones, r.id_estimacion)
            dias = (hoy - r.fecha_recepcion).days
            restantes = 15 - dias
            if dias >= 15:
                nivel = "CRITICA_VENCIDA (ROJA)"
                msg = f"Plazo legal de 15 días naturales VENCIDO ({dias} días transcurridos sin dictamen)."
            elif dias >= 10:
                nivel = "PREVENTIVA (AMARILLA)"
                msg = f"Alerta preventiva: Restan {restantes} días naturales para vencer el plazo legal de 15 días."
            else:
                nivel = "EN_PLAZO (VERDE)"
                msg = f"En plazo legal ({dias} días transcurridos, {restantes} restantes)."

            alertas.append(
                models.AlertaPlazoRevisionPublic(
                    id_revision=r.id_revision,
                    id_estimacion=r.id_estimacion,
                    id_obra=id_obra,
                    numero_estimacion=est.numero_estimacion if est else 0,
                    version_revisada=r.version_revisada,
                    fecha_recepcion=r.fecha_recepcion,
                    dias_transcurridos=dias,
                    dias_restantes_plazo_15=restantes,
                    nivel_alerta=nivel,
                    mensaje=msg
                )
            )
        return alertas

    @staticmethod
    def autorizar_pago_residente(
        session: Session,
        id_estimacion: int,
        aut_in: models.AutorizacionPagoInput,
        residente: Usuarios,
        ip_origen: str
    ) -> models.EstimacionPublic:
        """
        RF-RES-03 (RN-RES-03.1 y RN-RES-03.2): Autorización de pago por el Residente con firma electrónica,
        doble verificación presupuestal y candado Avance Físico >= Avance Financiero.
        """
        estimacion = EstimacionService.obtener_por_id(session, id_estimacion)
        cat_est = session.get(CatEstatus, estimacion.id_estatus)
        if not cat_est or cat_est.clave != "APROBADA":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RF-RES-03: La estimación debe contar con dictamen APROBADA por el Supervisor antes de autorizar su pago."
            )

        validar_firma_electronica_y_generar_sello(
            firma_plana=aut_in.firma_electronica_residente,
            firma_hash_usuario=residente.firma_electronica,
            id_usuario=residente.id_usuario,
            referencia=f"AUTORIZACION-PAGO-EST:{id_estimacion}"
        )

        # RN-RES-03.1: Doble verificación presupuestal y candado Físico >= Financiero
        obra = session.get(Obras, estimacion.id_obra)
        if not obra:
            raise HTTPException(status_code=404, detail="Obra no encontrada.")
        contrato = session.exec(select(Contratos).where(Contratos.id_obra == obra.id_obra)).first()
        techo = contrato.monto_contrato if contrato else obra.presupuesto_total

        id_rev_aprob = EstimacionService._obtener_estatus_id(session, "REVISION", "APROBADA")
        revs_aprob = list(
            session.exec(
                select(RevisionEstimaciones)
                .join(Estimaciones)
                .where(
                    Estimaciones.id_obra == obra.id_obra,
                    RevisionEstimaciones.id_estatus_revision == id_rev_aprob
                )
            ).all()
        )
        acumulado_neto = sum((r.monto_autorizado_neto for r in revs_aprob), Decimal("0.00"))
        if acumulado_neto > techo:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"RN-RES-03.1: El monto autorizado acumulado (${acumulado_neto:,.2f}) excede el techo contractual (${techo:,.2f})."
            )

        metricas = DirectivoFiniquitoService.calcular_avances_obra(session, obra)
        if metricas["pct_fin_real"] > metricas["pct_fisico_real"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Violación de control presupuestal: El avance financiero no puede superar al avance físico real ejecutado"
            )

        # RN-RES-03.2: Transición a AUTORIZADA_PAGO
        estimacion.id_estatus = EstimacionService._obtener_estatus_id(session, "ESTIMACION", "AUTORIZADA_PAGO")
        session.add(estimacion)
        session.commit()
        session.refresh(estimacion)

        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=residente.id_usuario,
            id_obra=estimacion.id_obra,
            tipo_accion="AUTORIZACION",
            accion_ejecutada=f"AUTORIZACION_PAGO_ESTIMACION_{id_estimacion}",
            descripcion=f"Autorización de pago por Residente para estimación #{estimacion.numero_estimacion}",
            ip_origen=ip_origen
        )
        return EstimacionService._enriquecer_estimacion(session, estimacion)


# ==========================================
# 4. SERVICIO: FACTURACIÓN CFDI Y LIQUIDACIÓN (RF-SUPT-06 y Estimaciones_Pagadas)
# ==========================================
class FacturacionPagoService:
    @staticmethod
    def adjuntar_cfdi(
        session: Session, factura_in: models.FacturacionEstimacionCreate
    ) -> FacturacionEstimacion:
        """
        RF-SUPT-06 (RN-SUPT-06.1 y RN-SUPT-06.2):
        - Precondición estricta: La estimación debe estar en estado AUTORIZADA_PAGO.
        - Par fiscal obligatorio: .pdf y .xml + folio_fiscal irrepetible.
        - Cuadre financiero: monto_factura == monto_autorizado_neto en Revision_Estimaciones.
        """
        estimacion = EstimacionService.obtener_por_id(session, factura_in.id_estimacion)
        cat_est = session.get(CatEstatus, estimacion.id_estatus)
        if not cat_est or cat_est.clave != "AUTORIZADA_PAGO":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RF-SUPT-06: Solo se pueden adjuntar archivos fiscales (CFDI) cuando la estimación tiene estatus AUTORIZADA_PAGO."
            )

        # RN-SUPT-06.1: Validar formatos .pdf y .xml
        validar_formato_y_tamano_archivo(factura_in.ruta_pdf, (".pdf",))
        validar_formato_y_tamano_archivo(factura_in.ruta_xml, (".xml",))

        existente_est = session.exec(
            select(FacturacionEstimacion).where(FacturacionEstimacion.id_estimacion == factura_in.id_estimacion)
        ).first()
        if existente_est:
            raise HTTPException(status_code=400, detail="Esta estimación ya cuenta con CFDI registrado.")

        existente_uuid = session.exec(
            select(FacturacionEstimacion).where(FacturacionEstimacion.folio_fiscal == factura_in.folio_fiscal)
        ).first()
        if existente_uuid:
            raise HTTPException(status_code=400, detail="RN-SUPT-06.1: El folio fiscal (UUID) ya está registrado.")

        # RN-SUPT-06.2: Cuadre financiero exacto contra monto_autorizado_neto
        rev_aprobada = session.exec(
            select(RevisionEstimaciones)
            .where(
                RevisionEstimaciones.id_estimacion == estimacion.id_estimacion,
                RevisionEstimaciones.version_revisada == estimacion.version_subsanacion
            )
        ).first()
        monto_esperado = rev_aprobada.monto_autorizado_neto if rev_aprobada else estimacion.monto_neto

        if _redondear_2(factura_in.monto_factura) != _redondear_2(monto_esperado):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"RN-SUPT-06.2: El monto de la factura (${factura_in.monto_factura:,.2f}) debe coincidir "
                    f"exactamente con el monto autorizado neto (${monto_esperado:,.2f})."
                )
            )

        nueva_factura = FacturacionEstimacion(
            id_estimacion=factura_in.id_estimacion,
            folio_fiscal=factura_in.folio_fiscal,
            monto_factura=factura_in.monto_factura,
            ruta_pdf=factura_in.ruta_pdf,
            ruta_xml=factura_in.ruta_xml
        )
        session.add(nueva_factura)
        session.commit()
        session.refresh(nueva_factura)
        return nueva_factura

    @staticmethod
    def registrar_liquidacion_pago(
        session: Session, pago_in: models.EstimacionPagadaCreate, usuario: Usuarios, ip_origen: str
    ) -> EstimacionesPagadas:
        """Registra la liquidación efectiva en Estimaciones_Pagadas y pasa la estimación a LIQUIDADA."""
        estimacion = EstimacionService.obtener_por_id(session, pago_in.id_estimacion)
        factura = session.exec(
            select(FacturacionEstimacion).where(FacturacionEstimacion.id_estimacion == pago_in.id_estimacion)
        ).first()
        if not factura:
            raise HTTPException(
                status_code=400,
                detail="No se puede liquidar una estimación que aún no cuenta con su factura CFDI (PDF y XML)."
            )

        if _redondear_2(pago_in.monto_pagado) != _redondear_2(factura.monto_factura):
            raise HTTPException(
                status_code=400,
                detail=f"El monto pagado (${pago_in.monto_pagado:,.2f}) debe coincidir con la factura (${factura.monto_factura:,.2f})."
            )

        id_est_liq_pago = EstimacionService._obtener_estatus_id(session, "PAGO", "LIQUIDADA")
        id_est_liq_est = EstimacionService._obtener_estatus_id(session, "ESTIMACION", "LIQUIDADA")

        nuevo_pago = EstimacionesPagadas(
            id_estimacion=pago_in.id_estimacion,
            id_estatus_pago=id_est_liq_pago,
            folio_estimacion=pago_in.folio_estimacion,
            monto_pagado=pago_in.monto_pagado,
            fecha_pago=pago_in.fecha_pago
        )
        estimacion.id_estatus = id_est_liq_est

        session.add(nuevo_pago)
        session.add(estimacion)
        session.commit()
        session.refresh(nuevo_pago)

        # Actualizar corte de avance financiero y físico
        DirectivoFiniquitoService.registrar_corte_avance(session, estimacion.id_obra, pago_in.fecha_pago)

        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=usuario.id_usuario,
            id_obra=estimacion.id_obra,
            tipo_accion="PAGO",
            accion_ejecutada=f"LIQUIDACION_ESTIMACION_{estimacion.id_estimacion}",
            descripcion=f"Liquidación de estimación #{estimacion.numero_estimacion} con folio {pago_in.folio_estimacion}",
            ip_origen=ip_origen
        )
        return nuevo_pago
