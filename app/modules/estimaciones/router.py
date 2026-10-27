from decimal import Decimal
from typing import List
from fastapi import APIRouter, Depends, status
from sqlmodel import Session
from app.core.database import get_session
from app.core.dependencies import (
    solo_admin,
    solo_superintendente,
    solo_supervisor,
    solo_residente,
    verificar_participacion_en_obra
)
from . import models, service

router = APIRouter(prefix="/estimaciones", tags=["03. Estimaciones, Generadores y Revisión Técnica"])


# --- 1. Catálogo de Tipos de Estimación ---
@router.post("/tipos", response_model=models.TipoEstimacionPublic, status_code=status.HTTP_201_CREATED)
def crear_tipo_estimacion(
    tipo_in: models.TipoEstimacionCreate,
    session: Session = Depends(get_session),
    admin=Depends(solo_admin)
):
    return service.TipoEstimacionService.crear(session, tipo_in)


@router.get("/tipos", response_model=List[models.TipoEstimacionPublic])
def listar_tipos_estimacion(session: Session = Depends(get_session)):
    return service.TipoEstimacionService.consultar(session)


@router.patch("/tipos/{id_tipo_estimacion}/desactivar", response_model=models.TipoEstimacionPublic)
def desactivar_tipo_estimacion(
    id_tipo_estimacion: int,
    session: Session = Depends(get_session),
    admin=Depends(solo_admin)
):
    return service.TipoEstimacionService.desactivar(session, id_tipo_estimacion)


# --- 2. Estimaciones ---
@router.post("/", response_model=models.EstimacionPublic, status_code=status.HTTP_201_CREATED)
def crear_borrador_estimacion(
    estimacion_in: models.EstimacionCreate,
    session: Session = Depends(get_session),
    current_user=Depends(solo_superintendente)
):
    verificar_participacion_en_obra(estimacion_in.id_obra, session, current_user)
    return service.EstimacionService.crear_borrador(session, estimacion_in)


@router.get("/obra/{id_obra}", response_model=List[models.EstimacionPublic])
def consultar_estimaciones_obra(
    id_obra: int,
    session: Session = Depends(get_session)
):
    return service.EstimacionService.consultar_por_obra(session, id_obra)


@router.get("/{id_estimacion}", response_model=models.EstimacionPublicDetalle)
def obtener_detalle_estimacion(
    id_estimacion: int,
    session: Session = Depends(get_session)
):
    return service.EstimacionService.obtener_por_id(session, id_estimacion)


@router.delete("/{id_estimacion}/borrador")
def eliminar_borrador_estimacion(
    id_estimacion: int,
    session: Session = Depends(get_session),
    current_user=Depends(solo_superintendente)
):
    return service.EstimacionService.eliminar_borrador(session, id_estimacion)


@router.patch("/{id_estimacion}/enviar-revision", response_model=models.EstimacionPublic)
def enviar_estimacion_a_revision(
    id_estimacion: int,
    session: Session = Depends(get_session),
    current_user=Depends(solo_superintendente)
):
    return service.EstimacionService.enviar_revision(session, id_estimacion)


@router.patch("/{id_estimacion}/autorizar-pago", response_model=models.EstimacionPublic)
def autorizar_pago_estimacion(
    id_estimacion: int,
    session: Session = Depends(get_session),
    current_user=Depends(solo_residente)
):
    return service.EstimacionService.autorizar_pago(session, id_estimacion)


# --- 3. Números Generadores y Validación ---
@router.post("/generadores", response_model=models.GeneradorPublic, status_code=status.HTTP_201_CREATED)
def crear_generador(
    gen_in: models.GeneradorCreate,
    session: Session = Depends(get_session),
    current_user=Depends(solo_superintendente)
):
    return service.GeneradorService.crear(session, gen_in)


@router.get("/{id_estimacion}/generadores", response_model=List[models.GeneradorPublic])
def consultar_generadores_estimacion(
    id_estimacion: int,
    session: Session = Depends(get_session)
):
    return service.GeneradorService.consultar_por_estimacion(session, id_estimacion)


@router.patch("/generadores/{id_generador}/corregir", response_model=models.GeneradorPublic)
def corregir_borrador_generador(
    id_generador: int,
    gen_in: models.GeneradorUpdate,
    session: Session = Depends(get_session),
    current_user=Depends(solo_superintendente)
):
    return service.GeneradorService.corregir_borrador(session, id_generador, gen_in)


@router.post(
    "/generadores/validaciones",
    response_model=models.GeneradorValidacionPublic,
    status_code=status.HTTP_201_CREATED
)
def registrar_dictamen_generador(
    val_in: models.GeneradorValidacionCreate,
    session: Session = Depends(get_session),
    current_user=Depends(solo_supervisor)
):
    return service.GeneradorService.registrar_dictamen_validacion(session, val_in)


# --- 4. Revisión Técnica (Supervisor) ---
@router.post("/revisiones", response_model=models.RevisionEstimacionPublic, status_code=status.HTTP_201_CREATED)
def emitir_dictamen_revision(
    rev_in: models.RevisionEstimacionCreate,
    session: Session = Depends(get_session),
    current_user=Depends(solo_supervisor)
):
    return service.RevisionEstimacionService.emitir_dictamen(session, rev_in)


@router.patch("/revisiones/{id_revision}/aprobar", response_model=models.RevisionEstimacionPublic)
def aprobar_revision_estimacion(
    id_revision: int,
    monto_autorizado_neto: Decimal,
    session: Session = Depends(get_session),
    current_user=Depends(solo_supervisor)
):
    return service.RevisionEstimacionService.aprobar(session, id_revision, monto_autorizado_neto)


@router.patch("/revisiones/{id_revision}/rechazar", response_model=models.RevisionEstimacionPublic)
def rechazar_revision_estimacion(
    id_revision: int,
    session: Session = Depends(get_session),
    current_user=Depends(solo_supervisor)
):
    return service.RevisionEstimacionService.rechazar(session, id_revision)


@router.get("/{id_estimacion}/revisiones", response_model=List[models.RevisionEstimacionPublic])
def consultar_revisiones_estimacion(
    id_estimacion: int,
    session: Session = Depends(get_session)
):
    return service.RevisionEstimacionService.consultar_por_estimacion(session, id_estimacion)


# --- 5. Facturación Fiscal (CFDI) ---
@router.post("/facturacion", response_model=models.FacturacionEstimacionPublic, status_code=status.HTTP_201_CREATED)
def adjuntar_factura_fiscal(
    factura_in: models.FacturacionEstimacionCreate,
    session: Session = Depends(get_session),
    current_user=Depends(solo_superintendente)
):
    return service.FacturacionEstimacionService.adjuntar_fiscal(session, factura_in)


@router.get("/{id_estimacion}/facturacion", response_model=models.FacturacionEstimacionPublic)
def consultar_factura_estimacion(
    id_estimacion: int,
    session: Session = Depends(get_session)
):
    return service.FacturacionEstimacionService.consultar_por_estimacion(session, id_estimacion)