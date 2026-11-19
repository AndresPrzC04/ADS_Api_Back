from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session, select
from app.core.database import get_session
from app.core.dependencies import (
    RequerirRoles,
    get_current_user,
    solo_residente,
    solo_superintendente,
    solo_supervisor,
    verificar_participacion_en_obra,
)
from app.models_base import FacturacionEstimacion, Usuarios
from . import models, service

router = APIRouter(
    prefix="/estimaciones",
    tags=["03. Estimaciones, Revisión Técnica, CFDI y Pagos"]
)


# --- 1. Estimaciones (RF-SUPT-03, RF-SUPT-07) ---
@router.post("/", response_model=models.EstimacionPublic, status_code=status.HTTP_201_CREATED)
def crear_borrador_estimacion(
    request: Request,
    estimacion_in: models.EstimacionCreate,
    session: Session = Depends(get_session),
    superintendente: Usuarios = Depends(solo_superintendente)
):
    verificar_participacion_en_obra(estimacion_in.id_obra, session, superintendente)
    ip = request.client.host if request.client else "127.0.0.1"
    return service.EstimacionService.crear_borrador(session, estimacion_in, superintendente, ip)


@router.patch("/{id_estimacion}/corregir", response_model=models.EstimacionPublic)
def corregir_estimacion_borrador_o_rechazada(
    id_estimacion: int,
    est_in: models.EstimacionUpdate,
    session: Session = Depends(get_session),
    superintendente: Usuarios = Depends(solo_superintendente)
):
    est = service.EstimacionService.obtener_por_id(session, id_estimacion)
    verificar_participacion_en_obra(est.id_obra, session, superintendente)
    return service.EstimacionService.corregir_borrador_o_rechazada(session, id_estimacion, est_in)


@router.get("/obra/{id_obra}", response_model=List[models.EstimacionPublic])
def consultar_estimaciones_obra(
    id_obra: int,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(get_current_user)
):
    verificar_participacion_en_obra(id_obra, session, current_user)
    return service.EstimacionService.consultar_por_obra(session, id_obra)


@router.get("/{id_estimacion}", response_model=models.EstimacionPublicDetalle)
def obtener_detalle_estimacion(
    id_estimacion: int,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(get_current_user)
):
    est = service.EstimacionService.obtener_por_id(session, id_estimacion)
    verificar_participacion_en_obra(est.id_obra, session, current_user)
    return service.EstimacionService.obtener_detalle_public(session, id_estimacion)


@router.delete("/{id_estimacion}/borrador")
def eliminar_borrador_estimacion(
    id_estimacion: int,
    session: Session = Depends(get_session),
    superintendente: Usuarios = Depends(solo_superintendente)
):
    est = service.EstimacionService.obtener_por_id(session, id_estimacion)
    verificar_participacion_en_obra(est.id_obra, session, superintendente)
    return service.EstimacionService.eliminar_borrador(session, id_estimacion)


@router.patch("/{id_estimacion}/enviar-revision", response_model=models.EstimacionPublic)
def enviar_estimacion_a_revision(
    id_estimacion: int,
    request: Request,
    session: Session = Depends(get_session),
    superintendente: Usuarios = Depends(solo_superintendente)
):
    est = service.EstimacionService.obtener_por_id(session, id_estimacion)
    verificar_participacion_en_obra(est.id_obra, session, superintendente)
    ip = request.client.host if request.client else "127.0.0.1"
    return service.EstimacionService.enviar_a_revision(session, id_estimacion, superintendente, ip)


# --- 2. Revisión Técnica del Supervisor y Plazos de 15 Días (RF-SUP-02, RF-SUP-06) ---
@router.post("/{id_estimacion}/dictaminar", response_model=models.RevisionEstimacionPublic)
def dictaminar_estimacion_supervisor(
    id_estimacion: int,
    request: Request,
    dictamen_in: models.DictamenRevisionInput,
    session: Session = Depends(get_session),
    supervisor: Usuarios = Depends(solo_supervisor)
):
    est = service.EstimacionService.obtener_por_id(session, id_estimacion)
    verificar_participacion_en_obra(est.id_obra, session, supervisor)
    ip = request.client.host if request.client else "127.0.0.1"
    return service.RevisionEstimacionService.dictaminar_estimacion(
        session, id_estimacion, dictamen_in, supervisor, ip
    )


@router.get("/{id_estimacion}/revisiones", response_model=List[models.RevisionEstimacionPublic])
def consultar_historial_revisiones_estimacion(
    id_estimacion: int,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(get_current_user)
):
    est = service.EstimacionService.obtener_por_id(session, id_estimacion)
    verificar_participacion_en_obra(est.id_obra, session, current_user)
    return service.RevisionEstimacionService.consultar_por_estimacion(session, id_estimacion)


@router.get("/obra/{id_obra}/alertas-plazo-15-dias", response_model=List[models.AlertaPlazoRevisionPublic])
def consultar_alertas_plazo_revision(
    id_obra: int,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(RequerirRoles(["SUPERVISOR", "RESIDENTE", "DIRECTIVO", "ADMINISTRADOR"]))
):
    verificar_participacion_en_obra(id_obra, session, current_user)
    return service.RevisionEstimacionService.consultar_alertas_plazo_15_dias(session, id_obra)


# --- 3. Autorización de Pago del Residente, CFDI y Liquidación (RF-RES-03, RF-SUPT-06) ---
@router.patch("/{id_estimacion}/autorizar-pago", response_model=models.EstimacionPublic)
def autorizar_pago_estimacion(
    id_estimacion: int,
    request: Request,
    aut_in: models.AutorizacionPagoInput,
    session: Session = Depends(get_session),
    residente: Usuarios = Depends(solo_residente)
):
    est = service.EstimacionService.obtener_por_id(session, id_estimacion)
    verificar_participacion_en_obra(est.id_obra, session, residente)
    ip = request.client.host if request.client else "127.0.0.1"
    return service.RevisionEstimacionService.autorizar_pago_residente(
        session, id_estimacion, aut_in, residente, ip
    )


@router.post("/facturacion", response_model=models.FacturacionEstimacionPublic, status_code=status.HTTP_201_CREATED)
def adjuntar_factura_cfdi(
    factura_in: models.FacturacionEstimacionCreate,
    session: Session = Depends(get_session),
    superintendente: Usuarios = Depends(solo_superintendente)
):
    est = service.EstimacionService.obtener_por_id(session, factura_in.id_estimacion)
    verificar_participacion_en_obra(est.id_obra, session, superintendente)
    return service.FacturacionPagoService.adjuntar_cfdi(session, factura_in)


@router.get("/{id_estimacion}/facturacion", response_model=models.FacturacionEstimacionPublic)
def consultar_factura_estimacion(
    id_estimacion: int,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(get_current_user)
):
    est = service.EstimacionService.obtener_por_id(session, id_estimacion)
    verificar_participacion_en_obra(est.id_obra, session, current_user)
    factura = session.exec(
        select(FacturacionEstimacion).where(FacturacionEstimacion.id_estimacion == id_estimacion)
    ).first()
    if not factura:
        raise HTTPException(status_code=404, detail="No se encontró comprobante fiscal CFDI para esta estimación.")
    return factura


@router.post("/pagos", response_model=models.EstimacionPagadaPublic, status_code=status.HTTP_201_CREATED)
def registrar_pago_liquidado(
    request: Request,
    pago_in: models.EstimacionPagadaCreate,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(RequerirRoles(["RESIDENTE", "ADMINISTRADOR"]))
):
    est = service.EstimacionService.obtener_por_id(session, pago_in.id_estimacion)
    verificar_participacion_en_obra(est.id_obra, session, current_user)
    ip = request.client.host if request.client else "127.0.0.1"
    return service.FacturacionPagoService.registrar_liquidacion_pago(
        session, pago_in, current_user, ip
    )
