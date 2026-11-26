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
    EvidenciaAdjunta,
    ObraConceptos,
    ReporteDiarioSupervision,
    ReporteIncidentes,
    Usuarios,
)
from . import models, service

router = APIRouter(
    prefix="/bitacora-expediente",
    tags=["04. Bitácora Electrónica Inmutable, Reportes de Supervisión, Evidencia y Calidad"]
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


# --- 2. Evidencia Fotográfica Adjunta (Bitácora o Reporte de Supervisión) ---
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
    return list(session.exec(select(EvidenciaAdjunta).where(EvidenciaAdjunta.id_nota == id_nota)).all())


@router.get("/reportes-diarios/{id_reporte}/evidencias", response_model=List[models.EvidenciaAdjuntaPublic])
def listar_evidencias_reporte(
    id_reporte: int,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(get_current_user)
):
    return list(session.exec(select(EvidenciaAdjunta).where(EvidenciaAdjunta.id_reporte == id_reporte)).all())


@router.delete("/evidencias/{id_evidencia}")
def eliminar_evidencia_adjunta(
    id_evidencia: int,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(roles_operativos_obra)
):
    return service.EvidenciaService.eliminar_evidencia(session, id_evidencia)


# --- 3. Reporte Diario de Supervisión con Ciclo de Firma y Avance Físico (RF-SUP-03) ---
@router.post(
    "/reportes-diarios",
    response_model=models.ReporteDiarioSupervisionPublic,
    status_code=status.HTTP_201_CREATED
)
def crear_reporte_borrador(
    reporte_in: models.ReporteDiarioSupervisionCreate,
    session: Session = Depends(get_session),
    supervisor: Usuarios = Depends(solo_supervisor)
):
    verificar_participacion_en_obra(reporte_in.id_obra, session, supervisor)
    return service.SupervisionCalidadService.crear_reporte_borrador(session, reporte_in, supervisor)


@router.patch(
    "/reportes-diarios/{id_reporte}",
    response_model=models.ReporteDiarioSupervisionPublic
)
def actualizar_reporte_sin_firma(
    id_reporte: int,
    reporte_in: models.ReporteDiarioSupervisionUpdate,
    session: Session = Depends(get_session),
    supervisor: Usuarios = Depends(solo_supervisor)
):
    reporte = session.get(ReporteDiarioSupervision, id_reporte)
    if reporte:
        verificar_participacion_en_obra(reporte.id_obra, session, supervisor)
    return service.SupervisionCalidadService.actualizar_reporte(session, id_reporte, reporte_in)


@router.patch(
    "/reportes-diarios/{id_reporte}/enviar",
    response_model=models.ReporteDiarioSupervisionPublic
)
def enviar_reporte_supervision(
    id_reporte: int,
    session: Session = Depends(get_session),
    supervisor: Usuarios = Depends(solo_supervisor)
):
    reporte = session.get(ReporteDiarioSupervision, id_reporte)
    if reporte:
        verificar_participacion_en_obra(reporte.id_obra, session, supervisor)
    return service.SupervisionCalidadService.enviar_reporte(session, id_reporte)


@router.patch(
    "/reportes-diarios/{id_reporte}/firmar",
    response_model=models.ReporteDiarioSupervisionPublic
)
def firmar_reporte_supervision(
    id_reporte: int,
    request: Request,
    firma_in: models.ReporteDiarioFirmaInput,
    session: Session = Depends(get_session),
    supervisor: Usuarios = Depends(solo_supervisor)
):
    reporte = session.get(ReporteDiarioSupervision, id_reporte)
    if reporte:
        verificar_participacion_en_obra(reporte.id_obra, session, supervisor)
    ip = request.client.host if request.client else "127.0.0.1"
    return service.SupervisionCalidadService.firmar_reporte(session, id_reporte, firma_in, supervisor, ip)


@router.patch(
    "/reportes-diarios/incidentes/{id_incidente}/estatus",
    response_model=models.ReporteIncidentePublic
)
def actualizar_estatus_incidente_reporte(
    id_incidente: int,
    estatus_in: models.ReporteIncidenteEstatusUpdate,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(roles_operativos_obra)
):
    inc = session.get(ReporteIncidentes, id_incidente)
    if inc:
        reporte = session.get(ReporteDiarioSupervision, inc.id_reporte)
        if reporte:
            verificar_participacion_en_obra(reporte.id_obra, session, current_user)
    return service.SupervisionCalidadService.actualizar_estatus_incidente(
        session, id_incidente, estatus_in
    )


@router.get("/obras/{id_obra}/reportes-diarios", response_model=List[models.ReporteDiarioSupervisionPublic])
def listar_reportes_diarios_obra(
    id_obra: int,
    skip: int = 0,
    limit: int = 20,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(get_current_user)
):
    verificar_participacion_en_obra(id_obra, session, current_user)
    return service.SupervisionCalidadService.consultar_reportes_diarios(
        session, id_obra, skip=skip, limit=limit
    )


# --- 4. Control de Calidad y Pruebas de Laboratorio (RF-SUP-03) ---
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
    conc = session.get(ObraConceptos, prueba_in.id_obra_concepto)
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
