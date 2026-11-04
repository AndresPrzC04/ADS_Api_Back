from typing import List
from fastapi import APIRouter, Depends, Request, status
from sqlmodel import Session, select
from app.core.database import get_session
from app.core.dependencies import (
     get_current_user,
    roles_operativos_obra,
    solo_supervisor,
    verificar_participacion_en_obra,
)
from app.models_base import (
    BitacoraNotas,
    ConceptosCatalogo,
    EvidenciaAdjunta,
    Usuarios,
)
from . import models, service

router = APIRouter(
    prefix="/bitacora-expediente",
    tags=["04. Bitácora Electrónica Inmutable, Evidencia Fotográfica, Calidad y Reporte Diario"]
)


# --- 1. Bitácora Electrónica de Obra Inmutable (RF-RES-01, RF-RES-02, RF-SUPT-05, RF-SUP-03) ---
@router.post("/notas", response_model=models.BitacoraNotaPublic, status_code=status.HTTP_201_CREATED)
def crear_nota_bitacora(
    request: Request,
    nota_in: models.BitacoraNotaCreate,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(roles_operativos_obra)
):
    verificar_participacion_en_obra(nota_in.id_obra, session, current_user)
    ip = request.client.host if request.client else "127.0.0.1"
    return service.BitacoraService.crear_nota(session, nota_in, current_user, ip)


@router.get("/obras/{id_obra}/notas", response_model=List[models.BitacoraNotaPublic])
def consultar_bitacora_paginada(
    id_obra: int,
    skip: int = 0,
    limit: int = 20,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(get_current_user)
):
    verificar_participacion_en_obra(id_obra, session, current_user)
    return service.BitacoraService.consultar_paginado(session, id_obra, skip=skip, limit=limit)


@router.patch("/notas/{id_nota}/firmar", response_model=models.BitacoraNotaPublic)
def firmar_nota_bitacora(
    id_nota: int,
    request: Request,
    firma_in: models.BitacoraNotaFirmaInput,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(roles_operativos_obra)
):
    nota = session.get(BitacoraNotas, id_nota)
    if nota:
        verificar_participacion_en_obra(nota.id_obra, session, current_user)
    ip = request.client.host if request.client else "127.0.0.1"
    return service.BitacoraService.firmar_nota(session, id_nota, firma_in, current_user, ip)


# --- 2. Evidencia Fotográfica Adjunta (RF-SUPT-04, RF-SUPT-05) ---
@router.post("/evidencias", response_model=models.EvidenciaAdjuntaPublic, status_code=status.HTTP_201_CREATED)
def agregar_evidencia_adjunta(
    ev_in: models.EvidenciaAdjuntaCreate,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(roles_operativos_obra)
):
    return service.EvidenciaService.agregar_evidencia(session, ev_in)


@router.get("/notas/{id_nota}/evidencias", response_model=List[models.EvidenciaAdjuntaPublic])
def listar_evidencias_nota(
    id_nota: int,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(get_current_user)
):
    return session.exec(select(EvidenciaAdjunta).where(EvidenciaAdjunta.id_nota == id_nota)).all()


@router.get("/generadores/{id_generador}/evidencias", response_model=List[models.EvidenciaAdjuntaPublic])
def listar_evidencias_generador(
    id_generador: int,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(get_current_user)
):
    return session.exec(select(EvidenciaAdjunta).where(EvidenciaAdjunta.id_generador == id_generador)).all()


@router.delete("/evidencias/{id_evidencia}")
def eliminar_evidencia_adjunta(
    id_evidencia: int,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(roles_operativos_obra)
):
    return service.EvidenciaService.eliminar_evidencia(session, id_evidencia)


# --- 3. Control de Calidad y Reportes Diarios de Supervisión (RF-SUP-03) ---
@router.post(
    "/calidad-pruebas",
    response_model=models.ControlCalidadPruebaPublic,
    status_code=status.HTTP_201_CREATED
)
def registrar_prueba_calidad(
    prueba_in: models.ControlCalidadPruebaCreate,
    session: Session = Depends(get_session),
    supervisor: Usuarios = Depends(solo_supervisor)
):
    conc = session.get(ConceptosCatalogo, prueba_in.id_concepto)
    if conc:
        verificar_participacion_en_obra(conc.id_obra, session, supervisor)
    return service.SupervisionCalidadService.registrar_prueba_calidad(session, prueba_in)


@router.get("/obras/{id_obra}/calidad-pruebas", response_model=List[models.ControlCalidadPruebaPublic])
def listar_pruebas_calidad_obra(
    id_obra: int,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(get_current_user)
):
    verificar_participacion_en_obra(id_obra, session, current_user)
    return service.SupervisionCalidadService.consultar_pruebas_obra(session, id_obra)


@router.post(
    "/reportes-diarios",
    response_model=models.ReporteDiarioSupervisionPublic,
    status_code=status.HTTP_201_CREATED
)
def crear_reporte_diario_supervision(
    reporte_in: models.ReporteDiarioSupervisionCreate,
    session: Session = Depends(get_session),
    supervisor: Usuarios = Depends(solo_supervisor)
):
    verificar_participacion_en_obra(reporte_in.id_obra, session, supervisor)
    return service.SupervisionCalidadService.crear_reporte_diario(session, reporte_in, supervisor)


@router.get("/obras/{id_obra}/reportes-diarios", response_model=List[models.ReporteDiarioSupervisionPublic])
def listar_reportes_diarios_obra(
    id_obra: int,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(get_current_user)
):
    verificar_participacion_en_obra(id_obra, session, current_user)
    return service.SupervisionCalidadService.consultar_reportes_diarios(session, id_obra)
