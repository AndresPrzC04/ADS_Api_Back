from typing import List
from fastapi import APIRouter, Depends, status
from sqlmodel import Session
from app.core.database import get_session
from app.core.dependencies import (
    solo_residente,
    solo_supervisor,
    roles_operativos_obra,
    RequerirRoles,
    verificar_participacion_en_obra
)
from . import models, service

router = APIRouter(
    prefix="/bitacora-expediente",
    tags=["04. Bitácora, Expediente Documental, Calidad y Evidencia"]
)


# --- 1. Bitácora Electrónica de Obra (Append-Only) ---
@router.post("/notas", response_model=models.BitacoraNotaPublic, status_code=status.HTTP_201_CREATED)
def crear_nota_bitacora(
    nota_in: models.BitacoraNotaCreate,
    session: Session = Depends(get_session),
    current_user=Depends(roles_operativos_obra)
):
    verificar_participacion_en_obra(nota_in.id_obra, session, current_user)
    if nota_in.tipo_nota.upper() in ["APERTURA", "CIERRE"] and current_user.rol.nombre.upper() != "RESIDENTE":
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el Residente tiene permiso exclusivo para emitir la nota de APERTURA o CIERRE."
        )
    return service.BitacoraService.crear(session, nota_in)


@router.get("/obras/{id_obra}/notas", response_model=List[models.BitacoraNotaPublic])
def consultar_bitacora_paginada(
    id_obra: int,
    skip: int = 0,
    limit: int = 50,
    session: Session = Depends(get_session)
):
    return service.BitacoraService.consultar_paginado(session, id_obra, skip=skip, limit=limit)


@router.patch("/notas/{id_nota}/firmar", response_model=models.BitacoraNotaPublic)
def firmar_nota_bitacora(
    id_nota: int,
    firma_in: models.BitacoraNotaFirma,
    session: Session = Depends(get_session),
    current_user=Depends(roles_operativos_obra)
):
    return service.BitacoraService.firmar(session, id_nota, firma_in)


@router.post(
    "/obras/{id_obra}/cerrar-bitacora",
    response_model=models.BitacoraNotaPublic,
    status_code=status.HTTP_201_CREATED
)
def cerrar_bitacora_obra(
    id_obra: int,
    descripcion_cierre: str,
    session: Session = Depends(get_session),
    residente=Depends(solo_residente)
):
    verificar_participacion_en_obra(id_obra, session, residente)
    return service.BitacoraService.cerrar_bitacora(
        session, id_obra, residente.id_usuario, descripcion_cierre
    )


# --- 2. Expediente Documental ---
@router.post("/documentos", response_model=models.ExpedienteDocumentoPublic, status_code=status.HTTP_201_CREATED)
def subir_documento_expediente(
    doc_in: models.ExpedienteDocumentoCreate,
    session: Session = Depends(get_session),
    current_user=Depends(RequerirRoles(["ADMINISTRADOR", "RESIDENTE", "SUPERVISOR"]))
):
    verificar_participacion_en_obra(doc_in.id_obra, session, current_user)
    return service.ExpedienteDocumentoService.subir(session, doc_in)


@router.get("/obras/{id_obra}/documentos", response_model=List[models.ExpedienteDocumentoPublic])
def consultar_expediente_obra(
    id_obra: int,
    session: Session = Depends(get_session)
):
    return service.ExpedienteDocumentoService.consultar_por_obra(session, id_obra)


@router.patch("/documentos/{id_documento}", response_model=models.ExpedienteDocumentoPublic)
def actualizar_estatus_documento(
    id_documento: int,
    doc_in: models.ExpedienteDocumentoUpdate,
    session: Session = Depends(get_session),
    current_user=Depends(RequerirRoles(["ADMINISTRADOR", "RESIDENTE"]))
):
    return service.ExpedienteDocumentoService.actualizar(session, id_documento, doc_in)


@router.delete("/documentos/{id_documento}")
def eliminar_documento_borrador(
    id_documento: int,
    session: Session = Depends(get_session),
    current_user=Depends(RequerirRoles(["ADMINISTRADOR", "RESIDENTE"]))
):
    return service.ExpedienteDocumentoService.eliminar(session, id_documento)


# --- 3. Archivos Adjuntos (Polimórfico: Bitácora, Generadores, Calidad) ---
@router.post("/adjuntos", response_model=models.ArchivoAdjuntoPublic, status_code=status.HTTP_201_CREATED)
def agregar_archivo_adjunto(
    adjunto_in: models.ArchivoAdjuntoCreate,
    session: Session = Depends(get_session),
    current_user=Depends(roles_operativos_obra)
):
    return service.ArchivoAdjuntoService.agregar(session, adjunto_in)


@router.get("/adjuntos/{entidad_tipo}/{entidad_id}", response_model=List[models.ArchivoAdjuntoPublic])
def consultar_adjuntos_por_entidad(
    entidad_tipo: str,
    entidad_id: int,
    session: Session = Depends(get_session)
):
    return service.ArchivoAdjuntoService.consultar_por_entidad(session, entidad_tipo, entidad_id)


@router.delete("/adjuntos/{id_archivo_adjunto}")
def eliminar_archivo_adjunto(
    id_archivo_adjunto: int,
    session: Session = Depends(get_session),
    current_user=Depends(roles_operativos_obra)
):
    return service.ArchivoAdjuntoService.eliminar(session, id_archivo_adjunto)


# --- 4. Control de Calidad y Reportes Diarios de Supervisión ---
@router.post(
    "/calidad-pruebas",
    response_model=models.ControlCalidadPruebaPublic,
    status_code=status.HTTP_201_CREATED
)
def registrar_prueba_calidad(
    prueba_in: models.ControlCalidadPruebaCreate,
    session: Session = Depends(get_session),
    supervisor=Depends(solo_supervisor)
):
    verificar_participacion_en_obra(prueba_in.id_obra, session, supervisor)
    return service.SupervisionCalidadService.registrar_ensayo(session, prueba_in)


@router.get("/obras/{id_obra}/calidad-pruebas", response_model=List[models.ControlCalidadPruebaPublic])
def listar_pruebas_calidad_obra(
    id_obra: int,
    session: Session = Depends(get_session)
):
    return service.SupervisionCalidadService.consultar_ensayos_obra(session, id_obra)


@router.post(
    "/reportes-diarios",
    response_model=models.ReporteDiarioSupervisionPublic,
    status_code=status.HTTP_201_CREATED
)
def crear_reporte_diario_supervision(
    reporte_in: models.ReporteDiarioSupervisionCreate,
    session: Session = Depends(get_session),
    supervisor=Depends(solo_supervisor)
):
    verificar_participacion_en_obra(reporte_in.id_obra, session, supervisor)
    return service.SupervisionCalidadService.crear_reporte_diario(session, reporte_in)


@router.get("/obras/{id_obra}/reportes-diarios", response_model=List[models.ReporteDiarioSupervisionPublic])
def listar_reportes_diarios_obra(
    id_obra: int,
    session: Session = Depends(get_session)
):
    return service.SupervisionCalidadService.consultar_reportes_diarios(session, id_obra)