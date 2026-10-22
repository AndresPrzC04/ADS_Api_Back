from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from . import schemas, service

router = APIRouter(
    prefix="/bitacora-expediente",
    tags=["04. Bitácora, Expediente Documental, Calidad y Evidencia"]
)


# --- 1. Bitácora Electrónica de Obra (Append-Only) ---
@router.post("/notas", response_model=schemas.BitacoraNotaPublic, status_code=status.HTTP_201_CREATED)
def crear_nota_bitacora(nota_in: schemas.BitacoraNotaCreate, db: Session = Depends(get_db)):
    return service.BitacoraService.crear(db, nota_in)


@router.get("/obras/{id_obra}/notas", response_model=List[schemas.BitacoraNotaPublic])
def consultar_bitacora_paginada(
    id_obra: int, skip: int = 0, limit: int = 50, db: Session = Depends(get_db)
):
    return service.BitacoraService.consultar_paginado(db, id_obra, skip=skip, limit=limit)


@router.patch("/notas/{id_nota}/firmar", response_model=schemas.BitacoraNotaPublic)
def firmar_nota_bitacora(
    id_nota: int, firma_in: schemas.BitacoraNotaFirma, db: Session = Depends(get_db)
):
    return service.BitacoraService.firmar(db, id_nota, firma_in)


@router.post("/obras/{id_obra}/cerrar-bitacora", response_model=schemas.BitacoraNotaPublic, status_code=status.HTTP_201_CREATED)
def cerrar_bitacora_obra(
    id_obra: int, id_residente_usuario: int, descripcion_cierre: str, db: Session = Depends(get_db)
):
    return service.BitacoraService.cerrar_bitacora(db, id_obra, id_residente_usuario, descripcion_cierre)


# --- 2. Expediente Documental ---
@router.post("/documentos", response_model=schemas.ExpedienteDocumentoPublic, status_code=status.HTTP_201_CREATED)
def subir_documento_expediente(doc_in: schemas.ExpedienteDocumentoCreate, db: Session = Depends(get_db)):
    return service.ExpedienteDocumentoService.subir(db, doc_in)


@router.get("/obras/{id_obra}/documentos", response_model=List[schemas.ExpedienteDocumentoPublic])
def consultar_expediente_obra(id_obra: int, db: Session = Depends(get_db)):
    return service.ExpedienteDocumentoService.consultar_por_obra(db, id_obra)


@router.patch("/documentos/{id_documento}", response_model=schemas.ExpedienteDocumentoPublic)
def actualizar_estatus_documento(
    id_documento: int, doc_in: schemas.ExpedienteDocumentoUpdate, db: Session = Depends(get_db)
):
    return service.ExpedienteDocumentoService.actualizar(db, id_documento, doc_in)


@router.delete("/documentos/{id_documento}")
def eliminar_documento_borrador(id_documento: int, db: Session = Depends(get_db)):
    return service.ExpedienteDocumentoService.eliminar(db, id_documento)


# --- 3. Archivos Adjuntos (Polimórfico: Bitácora, Generadores, Calidad) ---
@router.post("/adjuntos", response_model=schemas.ArchivoAdjuntoPublic, status_code=status.HTTP_201_CREATED)
def agregar_archivo_adjunto(adjunto_in: schemas.ArchivoAdjuntoCreate, db: Session = Depends(get_db)):
    return service.ArchivoAdjuntoService.agregar(db, adjunto_in)


@router.get("/adjuntos/{entidad_tipo}/{entidad_id}", response_model=List[schemas.ArchivoAdjuntoPublic])
def consultar_adjuntos_por_entidad(entidad_tipo: str, entidad_id: int, db: Session = Depends(get_db)):
    return service.ArchivoAdjuntoService.consultar_por_entidad(db, entidad_tipo, entidad_id)


@router.delete("/adjuntos/{id_archivo_adjunto}")
def eliminar_archivo_adjunto(id_archivo_adjunto: int, db: Session = Depends(get_db)):
    return service.ArchivoAdjuntoService.eliminar(db, id_archivo_adjunto)


# --- 4. Control de Calidad y Reportes Diarios de Supervisión ---
@router.post("/calidad-pruebas", response_model=schemas.ControlCalidadPruebaPublic, status_code=status.HTTP_201_CREATED)
def registrar_prueba_calidad(prueba_in: schemas.ControlCalidadPruebaCreate, db: Session = Depends(get_db)):
    return service.SupervisionCalidadService.registrar_ensayo(db, prueba_in)


@router.get("/obras/{id_obra}/calidad-pruebas", response_model=List[schemas.ControlCalidadPruebaPublic])
def listar_pruebas_calidad_obra(id_obra: int, db: Session = Depends(get_db)):
    return service.SupervisionCalidadService.consultar_ensayos_obra(db, id_obra)


@router.post("/reportes-diarios", response_model=schemas.ReporteDiarioSupervisionPublic, status_code=status.HTTP_201_CREATED)
def crear_reporte_diario_supervision(
    reporte_in: schemas.ReporteDiarioSupervisionCreate, db: Session = Depends(get_db)
):
    return service.SupervisionCalidadService.crear_reporte_diario(db, reporte_in)


@router.get("/obras/{id_obra}/reportes-diarios", response_model=List[schemas.ReporteDiarioSupervisionPublic])
def listar_reportes_diarios_obra(id_obra: int, db: Session = Depends(get_db)):
    return service.SupervisionCalidadService.consultar_reportes_diarios(db, id_obra)