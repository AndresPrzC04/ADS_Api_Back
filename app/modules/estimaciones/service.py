from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from sqlmodel import Session, col, or_, select
from app.core.security import (
    validar_firma_electronica_y_generar_sello,
    validar_formato_y_tamano_archivo,
)
from app.models_base import (
    BitacoraNotas,
    CatConceptosMaestro,
    CatEstatus,
    CatTipoEstimacion,
    CatTipoNotaBitacora,
    CatTipoPoliza,
    CatUnidadesMedida,
    Contratistas,
    Contratos,
    ControlCalidadPruebas,
    EstimacionDetalles,
    Estimaciones,
    EstimacionesPagadas,
    FacturacionEstimacion,
    ObraConceptos,
    Obras,
    ObrasAsignaciones,
    Polizas,
    ReporteDiarioSupervision,
    RevisionEstimaciones,
    RolUsuario,
    Usuarios,
)
from app.modules.obras_contratos.service import DirectivoFiniquitoService
from app.modules.usuarios_accesos.service import AuditoriaService
from . import models

TASA_IVA = Decimal("0.16")
TASA_RETENCION_SFP = Decimal("0.005")


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
    def _calcular_totales_financieros(
        monto_bruto: Decimal,
        monto_amortizacion: Decimal,
        retencion_atraso: Decimal,
    ) -> Tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]:
        bruto = _redondear_2(monto_bruto)
        amort = _redondear_2(monto_amortizacion)
        ret_atraso = _redondear_2(retencion_atraso)

        if amort > bruto:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El monto de amortización no puede ser mayor al monto bruto de la estimación."
            )

        iva = ((bruto - amort) * TASA_IVA).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        ret_sfp = (bruto * TASA_RETENCION_SFP).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        neto = (bruto - amort + iva - ret_atraso - ret_sfp).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if neto < Decimal("0.00"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Las deducciones y retenciones exceden el importe total de la estimación."
            )
        return bruto, amort, iva, ret_atraso, ret_sfp, neto

    @staticmethod
    def _validar_y_calcular_detalles(
        session: Session,
        id_obra: int,
        detalles_in: List[models.EstimacionDetalleCreate],
        id_estimacion_excluir: Optional[int] = None,
    ) -> Decimal:
        id_rech = EstimacionService._obtener_estatus_id(session, "ESTIMACION", "RECHAZADA")
        vistos: set[int] = set()
        monto_bruto_calc = Decimal("0.00")

        for item in detalles_in:
            if item.id_obra_concepto in vistos:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El concepto de obra ID {item.id_obra_concepto} está duplicado en el detalle."
                )
            vistos.add(item.id_obra_concepto)

            oc = session.get(ObraConceptos, item.id_obra_concepto)
            if not oc or oc.id_obra != id_obra:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Concepto de obra ID {item.id_obra_concepto} no encontrado en la obra."
                )

            stmt_prev = (
                select(EstimacionDetalles)
                .join(Estimaciones)
                .where(
                    EstimacionDetalles.id_obra_concepto == oc.id_obra_concepto,
                    Estimaciones.id_obra == id_obra,
                    col(Estimaciones.id_estatus) != id_rech,
                )
            )
            if id_estimacion_excluir is not None:
                stmt_prev = stmt_prev.where(
                    col(Estimaciones.id_estimacion) != id_estimacion_excluir
                )

            previos = list(session.exec(stmt_prev).all())
            acumulado_anterior = sum(
                (p.cantidad_estimada for p in previos), Decimal("0.00")
            )
            tope_cantidad = oc.cantidad_presupuestada + oc.cantidad_adicional_autorizada

            if (acumulado_anterior + item.cantidad_estimada) > tope_cantidad:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Volumen excedido para concepto de obra ID {oc.id_obra_concepto}: "
                        f"acumulado anterior ({acumulado_anterior}) + cantidad estimada ({item.cantidad_estimada}) "
                        f"supera el tope autorizado ({tope_cantidad})."
                    )
                )

            monto_bruto_calc += _redondear_2(item.cantidad_estimada * oc.precio_unitario)

        return _redondear_2(monto_bruto_calc)

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
            iva=est.iva,
            retencion_atraso=est.retencion_atraso,
            retencion_sfp=est.retencion_sfp,
            monto_neto=est.monto_neto
        )

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

        est_obra = session.get(CatEstatus, obra.id_estatus)
        if not est_obra or est_obra.clave != "EN_EJECUCION":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"RN-ADM-04.3 / RF-SUPT-03: No se pueden registrar estimaciones mientras la obra "
                    f"se encuentre en estado '{est_obra.clave if est_obra else 'DESCONOCIDO'}'. Debe estar EN_EJECUCION."
                )
            )

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

        tiene_catalogo = session.exec(
            select(ObraConceptos).where(ObraConceptos.id_obra == obra.id_obra)
        ).first()
        if not tiene_catalogo:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RF-SUPT-03: La obra debe contar con su Catálogo de Conceptos cargado."
            )

        if estimacion_in.periodo_fin < estimacion_in.periodo_inicio:
            raise HTTPException(status_code=400, detail="La fecha fin del periodo no puede ser menor a la de inicio.")

        if estimacion_in.detalles:
            monto_bruto_base = EstimacionService._validar_y_calcular_detalles(
                session=session,
                id_obra=obra.id_obra,
                detalles_in=estimacion_in.detalles,
            )
        elif estimacion_in.monto_bruto is not None:
            monto_bruto_base = estimacion_in.monto_bruto
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debe enviar 'detalles' por concepto o capturar 'monto_bruto' mayor a 0."
            )

        bruto, amort, iva_calc, ret_atraso, ret_sfp, neto_calc = (
            EstimacionService._calcular_totales_financieros(
                monto_bruto=monto_bruto_base,
                monto_amortizacion=estimacion_in.monto_amortizacion,
                retencion_atraso=estimacion_in.retencion_atraso,
            )
        )

        tipo_est = session.get(CatTipoEstimacion, estimacion_in.id_tipo_estimacion)
        if not tipo_est or not tipo_est.activo:
            raise HTTPException(status_code=404, detail="Tipo de estimación no encontrado o inactivo.")

        # RN-SUPT-03.7: Secuencia y no traslape de periodos en estimaciones ordinarias
        duplicado_num = session.exec(
            select(Estimaciones).where(
                Estimaciones.id_obra == obra.id_obra,
                Estimaciones.numero_estimacion == estimacion_in.numero_estimacion
            )
        ).first()
        if duplicado_num:
            raise HTTPException(
                status_code=400,
                detail=f"RN-SUPT-03.7: Ya existe la estimación #{estimacion_in.numero_estimacion} en esta obra."
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
                            f"RN-SUPT-03.7: El periodo ({estimacion_in.periodo_inicio} a {estimacion_in.periodo_fin}) "
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
            monto_bruto=bruto,
            monto_amortizacion=amort,
            iva=iva_calc,
            retencion_atraso=ret_atraso,
            retencion_sfp=ret_sfp,
            monto_neto=neto_calc
        )
        session.add(nueva)
        session.flush()

        for det in estimacion_in.detalles:
            session.add(
                EstimacionDetalles(
                    id_estimacion=nueva.id_estimacion,
                    id_obra_concepto=det.id_obra_concepto,
                    cantidad_estimada=_redondear_2(det.cantidad_estimada),
                )
            )

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
    def corregir_borrador_o_rechazada(
        session: Session, id_estimacion: int, est_in: models.EstimacionUpdate
    ) -> models.EstimacionPublic:
        """RF-SUPT-07: Permite al Superintendente ajustar montos y detalles en BORRADOR o tras un RECHAZO."""
        est = EstimacionService.obtener_por_id(session, id_estimacion)
        cat_est = session.get(CatEstatus, est.id_estatus)
        if not cat_est or cat_est.clave not in {"BORRADOR", "RECHAZADA", "OBSERVADA"}:
            raise HTTPException(
                status_code=400,
                detail="RNF-SEG-02: Solo se pueden corregir estimaciones en estado BORRADOR o RECHAZADA."
            )

        nuevo_bruto = est.monto_bruto
        if est_in.detalles is not None:
            if est_in.detalles:
                nuevo_bruto = EstimacionService._validar_y_calcular_detalles(
                    session=session,
                    id_obra=est.id_obra,
                    detalles_in=est_in.detalles,
                    id_estimacion_excluir=est.id_estimacion,
                )
            elif est_in.monto_bruto is not None:
                nuevo_bruto = est_in.monto_bruto

            prev_detalles = list(
                session.exec(
                    select(EstimacionDetalles).where(
                        EstimacionDetalles.id_estimacion == est.id_estimacion
                    )
                ).all()
            )
            for d_prev in prev_detalles:
                session.delete(d_prev)
            session.flush()
            for det in est_in.detalles:
                session.add(
                    EstimacionDetalles(
                        id_estimacion=est.id_estimacion,
                        id_obra_concepto=det.id_obra_concepto,
                        cantidad_estimada=_redondear_2(det.cantidad_estimada),
                    )
                )
        elif est_in.monto_bruto is not None:
            nuevo_bruto = est_in.monto_bruto

        nueva_amort = (
            est_in.monto_amortizacion
            if est_in.monto_amortizacion is not None
            else est.monto_amortizacion
        )
        nueva_ret_atraso = (
            est_in.retencion_atraso
            if est_in.retencion_atraso is not None
            else est.retencion_atraso
        )

        bruto, amort, iva_calc, ret_atraso, ret_sfp, neto_calc = (
            EstimacionService._calcular_totales_financieros(
                monto_bruto=nuevo_bruto,
                monto_amortizacion=nueva_amort,
                retencion_atraso=nueva_ret_atraso,
            )
        )
        est.monto_bruto = bruto
        est.monto_amortizacion = amort
        est.iva = iva_calc
        est.retencion_atraso = ret_atraso
        est.retencion_sfp = ret_sfp
        est.monto_neto = neto_calc

        session.add(est)
        session.commit()
        session.refresh(est)
        return EstimacionService._enriquecer_estimacion(session, est)

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
        detalles = list(
            session.exec(
                select(EstimacionDetalles)
                .where(EstimacionDetalles.id_estimacion == id_estimacion)
                .order_by(col(EstimacionDetalles.id_estimacion_detalle).asc())
            ).all()
        )
        revisiones = RevisionEstimacionService.consultar_por_estimacion(session, id_estimacion)
        factura = session.exec(
            select(FacturacionEstimacion).where(FacturacionEstimacion.id_estimacion == id_estimacion)
        ).first()
        pago = session.get(EstimacionesPagadas, id_estimacion)

        return models.EstimacionPublicDetalle(
            **base.model_dump(),
            detalles=[models.EstimacionDetallePublic(**d.model_dump()) for d in detalles],
            revisiones=revisiones,
            facturacion=models.FacturacionEstimacionPublic(**factura.model_dump()) if factura else None,
            pago=models.EstimacionPagadaPublic(**pago.model_dump()) if pago else None
        )

    @staticmethod
    def obtener_caratula(
        session: Session, id_estimacion: int
    ) -> models.EstimacionCaratulaPublic:
        """Calcula en vivo la carátula completa de la estimación por consulta + cálculo (sin duplicar datos en BD)."""
        est = EstimacionService.obtener_por_id(session, id_estimacion)
        obra = session.get(Obras, est.id_obra)
        if not obra:
            raise HTTPException(status_code=404, detail="Obra no encontrada.")

        contrato = session.exec(
            select(Contratos).where(Contratos.id_obra == est.id_obra)
        ).first()
        contratista = (
            session.get(Contratistas, contrato.id_contratista) if contrato else None
        )

        numero_fianza_anticipo: Optional[str] = None
        if contrato:
            tipo_pol_ant = session.exec(
                select(CatTipoPoliza).where(CatTipoPoliza.clave == "ANTICIPO")
            ).first()
            if tipo_pol_ant:
                poliza_ant = session.exec(
                    select(Polizas).where(
                        Polizas.id_contrato == contrato.id_contrato,
                        Polizas.id_tipo_poliza == tipo_pol_ant.id_tipo_poliza,
                    )
                ).first()
                if poliza_ant:
                    numero_fianza_anticipo = poliza_ant.numero_poliza

        monto_contrato = contrato.monto_contrato if contrato else obra.presupuesto_total
        monto_anticipo = contrato.monto_anticipo if contrato else Decimal("0.00")

        tipo_est = session.get(CatTipoEstimacion, est.id_tipo_estimacion)
        tipo_estimacion_str = tipo_est.clave if tipo_est else "ORDINARIA"

        id_rech = EstimacionService._obtener_estatus_id(session, "ESTIMACION", "RECHAZADA")
        estimaciones_anteriores = list(
            session.exec(
                select(Estimaciones).where(
                    Estimaciones.id_obra == est.id_obra,
                    col(Estimaciones.numero_estimacion) < est.numero_estimacion,
                    col(Estimaciones.id_estatus) != id_rech,
                )
            ).all()
        )

        importe_estimado = _redondear_2(est.monto_bruto)
        acumulado_anterior = _redondear_2(
            sum((e.monto_bruto for e in estimaciones_anteriores), Decimal("0.00"))
        )
        acumulado_actual = _redondear_2(acumulado_anterior + importe_estimado)
        saldo_por_estimar = _redondear_2(max(Decimal("0.00"), monto_contrato - acumulado_actual))

        amortizacion_actual = _redondear_2(est.monto_amortizacion)
        amortizacion_acumulada_anterior = _redondear_2(
            sum((e.monto_amortizacion for e in estimaciones_anteriores), Decimal("0.00"))
        )
        amortizacion_acumulada_actual = _redondear_2(
            amortizacion_acumulada_anterior + amortizacion_actual
        )
        saldo_por_amortizar = _redondear_2(
            max(Decimal("0.00"), monto_anticipo - amortizacion_acumulada_actual)
        )

        ids_est_anteriores = [e.id_estimacion for e in estimaciones_anteriores]
        detalles_est = list(
            session.exec(
                select(EstimacionDetalles)
                .where(EstimacionDetalles.id_estimacion == est.id_estimacion)
                .order_by(col(EstimacionDetalles.id_estimacion_detalle).asc())
            ).all()
        )

        detalles_caratula: List[models.EstimacionCaratulaDetallePublic] = []
        for det in detalles_est:
            oc = session.get(ObraConceptos, det.id_obra_concepto)
            maestro = (
                session.get(CatConceptosMaestro, oc.id_concepto_maestro) if oc else None
            )
            unidad_obj = (
                session.get(CatUnidadesMedida, maestro.id_unidad) if maestro else None
            )

            if ids_est_anteriores:
                det_prevs = list(
                    session.exec(
                        select(EstimacionDetalles).where(
                            EstimacionDetalles.id_obra_concepto == det.id_obra_concepto,
                            col(EstimacionDetalles.id_estimacion).in_(ids_est_anteriores),
                        )
                    ).all()
                )
                det_acum_ant = _redondear_2(
                    sum((dp.cantidad_estimada for dp in det_prevs), Decimal("0.00"))
                )
            else:
                det_acum_ant = Decimal("0.00")

            det_cant = _redondear_2(det.cantidad_estimada)
            det_acum_act = _redondear_2(det_acum_ant + det_cant)
            tope_cant = (
                (oc.cantidad_presupuestada + oc.cantidad_adicional_autorizada)
                if oc
                else Decimal("0.00")
            )
            det_saldo = _redondear_2(max(Decimal("0.00"), tope_cant - det_acum_act))
            pu = _redondear_2(oc.precio_unitario) if oc else Decimal("0.00")
            det_importe = _redondear_2(det_cant * pu)

            detalles_caratula.append(
                models.EstimacionCaratulaDetallePublic(
                    id_obra_concepto=det.id_obra_concepto,
                    clave_concepto=maestro.clave_concepto if maestro else "",
                    descripcion=maestro.descripcion if maestro else "",
                    unidad=unidad_obj.clave if unidad_obj else "",
                    acumulado_anterior=det_acum_ant,
                    cantidad_estimada=det_cant,
                    acumulado_actual=det_acum_act,
                    saldo=det_saldo,
                    precio_unitario=pu,
                    importe=det_importe,
                )
            )

        return models.EstimacionCaratulaPublic(
            numero_contrato=contrato.numero_contrato if contrato else None,
            razon_social_contratista=contratista.razon_social if contratista else None,
            rfc_contratista=contratista.rfc if contratista else None,
            numero_fianza_anticipo=numero_fianza_anticipo,
            monto_contrato=_redondear_2(monto_contrato),
            monto_anticipo=_redondear_2(monto_anticipo),
            fecha_presentacion=est.fecha_presentacion,
            numero_estimacion=est.numero_estimacion,
            tipo_estimacion=tipo_estimacion_str,
            importe_estimado=importe_estimado,
            acumulado_anterior=acumulado_anterior,
            acumulado_actual=acumulado_actual,
            saldo_por_estimar=saldo_por_estimar,
            amortizacion_actual=amortizacion_actual,
            amortizacion_acumulada_anterior=amortizacion_acumulada_anterior,
            amortizacion_acumulada_actual=amortizacion_acumulada_actual,
            saldo_por_amortizar=saldo_por_amortizar,
            iva=_redondear_2(est.iva),
            retencion_atraso=_redondear_2(est.retencion_atraso),
            retencion_sfp=_redondear_2(est.retencion_sfp),
            total_neto=_redondear_2(est.monto_neto),
            detalles=detalles_caratula,
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
        detalles_prev = list(
            session.exec(
                select(EstimacionDetalles).where(
                    EstimacionDetalles.id_estimacion == est.id_estimacion
                )
            ).all()
        )
        for d in detalles_prev:
            session.delete(d)
        session.flush()
        session.delete(est)
        session.commit()
        return {"detalle": f"Estimación {id_estimacion} en borrador eliminada correctamente."}

    @staticmethod
    def enviar_a_revision(
        session: Session, id_estimacion: int, superintendente: Usuarios, ip_origen: str
    ) -> models.EstimacionPublic:
        """
        RN-SUPT-03.8, RN-SUPT-03.9, RN-SUPT-07.2 y RN-SUP-06.1:
        - Verifica que exista al menos un Reporte de Supervisión FIRMADO dentro del periodo de la estimación.
        - Verifica que el acumulado bruto no rebase el importe equivalente al avance físico real firmado.
        - Si proviene de RECHAZADA, incrementa version_subsanacion y crea un nuevo registro en Revision_Estimaciones.
        """
        est = EstimacionService.obtener_por_id(session, id_estimacion)
        obra = session.get(Obras, est.id_obra)
        if not obra:
            raise HTTPException(status_code=404, detail="Obra no encontrada.")

        est_obra = session.get(CatEstatus, obra.id_estatus)
        if est_obra and est_obra.clave != "EN_EJECUCION":
            raise HTTPException(
                status_code=400,
                detail=f"La obra se encuentra en estado '{est_obra.clave}'; no se pueden enviar estimaciones a revisión."
            )

        cat_est = session.get(CatEstatus, est.id_estatus)
        clave_actual = cat_est.clave if cat_est else ""
        if clave_actual not in {"BORRADOR", "RECHAZADA", "OBSERVADA"}:
            raise HTTPException(
                status_code=400,
                detail=f"La estimación en estado '{clave_actual}' no puede enviarse a revisión."
            )

        # RN-SUPT-03.8: Debe existir al menos un Reporte de Supervisión FIRMADO dentro del periodo (3NF)
        id_rep_firmado = EstimacionService._obtener_estatus_id(session, "REPORTE", "FIRMADO")
        reporte_respaldo = session.exec(
            select(ReporteDiarioSupervision).where(
                ReporteDiarioSupervision.id_obra == est.id_obra,
                ReporteDiarioSupervision.id_estatus_reporte == id_rep_firmado,
                col(ReporteDiarioSupervision.fecha_reporte) >= est.periodo_inicio,
                col(ReporteDiarioSupervision.fecha_reporte) <= est.periodo_fin,
            )
        ).first()
        if not reporte_respaldo:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"RN-SUPT-03.8: Para enviar a revisión debe existir al menos un Reporte de Supervisión "
                    f"FIRMADO dentro del periodo ({est.periodo_inicio} a {est.periodo_fin})."
                )
            )

        # RN-SUPT-03.9: El importe bruto acumulado no puede rebasar el equivalente al avance físico vigente
        pct_fisico_vigente = DirectivoFiniquitoService.obtener_ultimo_avance_fisico(session, obra.id_obra)
        importe_fisico_equivalente = _redondear_2(
            (pct_fisico_vigente / Decimal("100.00")) * obra.presupuesto_total
        )

        otras_estimaciones = list(
            session.exec(
                select(Estimaciones).where(
                    Estimaciones.id_obra == obra.id_obra,
                    col(Estimaciones.id_estimacion) != est.id_estimacion
                )
            ).all()
        )
        # Sumar estimaciones activas (no rechazadas)
        id_rech = EstimacionService._obtener_estatus_id(session, "ESTIMACION", "RECHAZADA")
        bruto_previo = sum(
            (e.monto_bruto for e in otras_estimaciones if e.id_estatus != id_rech),
            Decimal("0.00")
        )
        if (bruto_previo + est.monto_bruto) > importe_fisico_equivalente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"RN-SUPT-03.9: El importe bruto acumulado (${bruto_previo + est.monto_bruto:,.2f}) "
                    f"excede el monto equivalente al avance físico real firmado ({pct_fisico_vigente}% = ${importe_fisico_equivalente:,.2f})."
                )
            )

        if clave_actual in {"RECHAZADA", "OBSERVADA"}:
            est.version_subsanacion += 1

        bruto, amort, iva_calc, ret_atraso, ret_sfp, neto_calc = (
            EstimacionService._calcular_totales_financieros(
                monto_bruto=est.monto_bruto,
                monto_amortizacion=est.monto_amortizacion,
                retencion_atraso=est.retencion_atraso,
            )
        )
        est.monto_bruto = bruto
        est.monto_amortizacion = amort
        est.iva = iva_calc
        est.retencion_atraso = ret_atraso
        est.retencion_sfp = ret_sfp
        est.monto_neto = neto_calc
        est.id_estatus = EstimacionService._obtener_estatus_id(session, "ESTIMACION", "EN_REVISION")
        est.fecha_presentacion = date.today()
        session.add(est)

        # RN-SUP-06.1: Estampar fecha_recepcion en Revision_Estimaciones
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
# 2. SERVICIO: REVISIÓN TÉCNICA, CANDADO FINANCIERO Y AUTORIZACIÓN DE PAGO (RF-SUP-02, RF-SUP-06, RF-RES-03)
# ==========================================
class RevisionEstimacionService:
    @staticmethod
    def _obra_tiene_ensayo_rechazado(session: Session, id_obra: int) -> bool:
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
    def dictaminar_estimacion(
        session: Session,
        id_estimacion: int,
        dictamen_in: models.DictamenRevisionInput,
        supervisor: Usuarios,
        ip_origen: str
    ) -> models.RevisionEstimacionPublic:
        """
        RF-SUP-02 (Sin Generadores ni Retenciones RF-SUP-05):
        - Exige firma electrónica del Supervisor.
        - Si APROBADA: verifica candado Avance Financiero Real <= Avance Físico Real (Avances_Fisicos)
          y registra un nuevo corte actualizado en Avances_Fisicos.
        - Si RECHAZADA: exige observaciones_rechazo y desbloquea la estimación para subsanación (RF-SUPT-07).
        """
        estimacion = EstimacionService.obtener_por_id(session, id_estimacion)
        cat_est = session.get(CatEstatus, estimacion.id_estatus)
        if not cat_est or cat_est.clave != "EN_REVISION":
            raise HTTPException(
                status_code=400,
                detail="La estimación debe estar en estado EN_REVISION para emitir dictamen."
            )

        sello = validar_firma_electronica_y_generar_sello(
            firma_plana=dictamen_in.firma_electronica_supervisor,
            firma_hash_usuario=supervisor.firma_electronica,
            id_usuario=supervisor.id_usuario,
            referencia=f"REVISION-EST:{id_estimacion}-V{estimacion.version_subsanacion}"
        )

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
            session.refresh(revision)
            return models.RevisionEstimacionPublic(
                **revision.model_dump(),
                clave_estatus_revision="RECHAZADA"
            )

        # Caso APROBADA
        monto_aut_neto = (
            _redondear_2(dictamen_in.monto_autorizado_neto)
            if dictamen_in.monto_autorizado_neto is not None
            else estimacion.monto_neto
        )
        if monto_aut_neto > estimacion.monto_neto:
            raise HTTPException(
                status_code=400,
                detail="El monto autorizado neto no puede ser mayor al monto neto solicitado en la estimación."
            )

        obra = session.get(Obras, estimacion.id_obra)
        if not obra:
            raise HTTPException(status_code=404, detail="Obra no encontrada.")

        # RN-DIR-01.6 y RN-SUP-02.2: Candado Avance Financiero Real <= Avance Físico Real
        pct_fisico_real = DirectivoFiniquitoService.obtener_ultimo_avance_fisico(session, obra.id_obra)
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

        if nuevo_pct_fin > pct_fisico_real:
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

        # Actualizar corte en Avances_Fisicos manteniendo el porcentaje_fisico vigente
        DirectivoFiniquitoService.registrar_corte_avance(
            session=session,
            id_obra=obra.id_obra,
            porcentaje_fisico_nuevo=pct_fisico_real,
            fecha_corte=date.today()
        )

        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=supervisor.id_usuario,
            id_obra=estimacion.id_obra,
            tipo_accion="FIRMA",
            accion_ejecutada=f"APROBACION_ESTIMACION_{id_estimacion}_V{estimacion.version_subsanacion}",
            descripcion=f"Aprobación técnica de estimación #{estimacion.numero_estimacion} por ${monto_aut_neto:,.2f}",
            ip_origen=ip_origen
        )

        advertencia = None
        if RevisionEstimacionService._obra_tiene_ensayo_rechazado(session, obra.id_obra):
            advertencia = (
                "ADVERTENCIA (RN-SUP-03.3): La obra cuenta con pruebas de laboratorio dictaminadas como RECHAZADO."
            )

        session.refresh(revision)
        return models.RevisionEstimacionPublic(
            **revision.model_dump(),
            clave_estatus_revision="APROBADA",
            advertencia_calidad=advertencia
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
# 3. SERVICIO: FACTURACIÓN CFDI Y LIQUIDACIÓN (RF-SUPT-06 y Estimaciones_Pagadas)
# ==========================================
class FacturacionPagoService:
    @staticmethod
    def adjuntar_cfdi(
        session: Session, factura_in: models.FacturacionEstimacionCreate
    ) -> FacturacionEstimacion:
        estimacion = EstimacionService.obtener_por_id(session, factura_in.id_estimacion)
        cat_est = session.get(CatEstatus, estimacion.id_estatus)
        if not cat_est or cat_est.clave != "AUTORIZADA_PAGO":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RF-SUPT-06: Solo se pueden adjuntar archivos fiscales (CFDI) cuando la estimación tiene estatus AUTORIZADA_PAGO."
            )

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

        # Actualizar corte de avance financiero manteniendo el avance físico vigente
        DirectivoFiniquitoService.registrar_corte_avance(
            session=session,
            id_obra=estimacion.id_obra,
            porcentaje_fisico_nuevo=None,
            fecha_corte=pago_in.fecha_pago
        )

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
