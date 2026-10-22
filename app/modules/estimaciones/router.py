from decimal import Decimal
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from . import schemas, service

router = APIRouter(prefix="/estimaciones", tags=["03. Estimaciones, Generadores y Revisión Técnica"])


# --- 1. Catálogo de Tipos de Estimación ---
@router.post("/tipos", response_model=schemas.TipoEstimacionPublic, status_code=status.HTTP_201_CREATED)
def crear_tipo_estimacion(tipo_in: schemas.TipoEstimacionCreate, db: Session = Depends(get_db)):
    return service.TipoEstimacionService.crear(db, tipo_in)


@router.get("/tipos", response_model=List[schemas.TipoEstimacionPublic])
def listar_tipos_estimacion(db: Session = Depends(get_db)):
    return service.TipoEstimacionService.consultar(db)


@router.patch("/tipos/{id_tipo_estimacion}/desactivar", response_model=schemas.TipoEstimacionPublic)
def desactivar_tipo_estimacion(id_tipo_estimacion: int, db: Session = Depends(get_db)):
    return service.TipoEstimacionService.desactivar(db, id_tipo_estimacion)


# --- 2. Gestión de Estimaciones ---
@router.post("/", response_model=schemas.EstimacionPublic, status_code=status.HTTP_201_CREATED)
def crear_borrador_estimacion(estimacion_in: schemas.EstimacionCreate, db: Session = Depends(get_db)):
    return service.EstimacionService.crear_borrador(db, estimacion_in)


@router.get("/obra/{id_obra}", response_model=List[schemas.EstimacionPublic])
def consultar_estimaciones_obra(id_obra: int, db: Session = Depends(get_db)):
    return service.EstimacionService.consultar_por_obra(db, id_obra)


@router.get("/{id_estimacion}", response_model=schemas.EstimacionPublic)
def obtener_detalle_estimacion(id_estimacion: int, db: Session = Depends(get_db)):
    return service.EstimacionService.obtener_por_id(db, id_estimacion)


@router.delete("/{id_estimacion}/borrador")
def eliminar_borrador_estimacion(id_estimacion: int, db: Session = Depends(get_db)):
    return service.EstimacionService.eliminar_borrador(db, id_estimacion)


@router.patch("/{id_estimacion}/enviar-revision", response_model=schemas.EstimacionPublic)
def enviar_estimacion_a_revision(id_estimacion: int, db: Session = Depends(get_db)):
    return service.EstimacionService.enviar_revision(db, id_estimacion)


@router.patch("/{id_estimacion}/autorizar-pago", response_model=schemas.EstimacionPublic)
def autorizar_pago_estimacion(id_estimacion: int, db: Session = Depends(get_db)):
    return service.EstimacionService.autorizar_pago(db, id_estimacion)


# --- 3. Números Generadores y Validación ---
@router.post("/generadores", response_model=schemas.GeneradorPublic, status_code=status.HTTP_201_CREATED)
def crear_generador(gen_in: schemas.GeneradorCreate, db: Session = Depends(get_db)):
    return service.GeneradorService.crear(db, gen_in)


@router.get("/{id_estimacion}/generadores", response_model=List[schemas.GeneradorPublic])
def consultar_generadores_estimacion(id_estimacion: int, db: Session = Depends(get_db)):
    return service.GeneradorService.consultar_por_estimacion(db, id_estimacion)


@router.patch("/generadores/{id_generador}/corregir", response_model=schemas.GeneradorPublic)
def corregir_borrador_generador(
    id_generador: int, gen_in: schemas.GeneradorUpdate, db: Session = Depends(get_db)
):
    return service.GeneradorService.corregir_borrador(db, id_generador, gen_in)


@router.post("/generadores/validaciones", response_model=schemas.GeneradorValidacionPublic, status_code=status.HTTP_201_CREATED)
def registrar_dictamen_generador(val_in: schemas.GeneradorValidacionCreate, db: Session = Depends(get_db)):
    return service.GeneradorService.registrar_dictamen_validacion(db, val_in)


# --- 4. Revisión Técnica (Supervisor) ---
@router.post("/revisiones", response_model=schemas.RevisionEstimacionPublic, status_code=status.HTTP_201_CREATED)
def emitir_dictamen_revision(rev_in: schemas.RevisionEstimacionCreate, db: Session = Depends(get_db)):
    return service.RevisionEstimacionService.emitir_dictamen(db, rev_in)


@router.patch("/revisiones/{id_revision}/aprobar", response_model=schemas.RevisionEstimacionPublic)
def aprobar_revision_estimacion(
    id_revision: int, monto_autorizado_neto: Decimal, db: Session = Depends(get_db)
):
    return service.RevisionEstimacionService.aprobar(db, id_revision, monto_autorizado_neto)


@router.patch("/revisiones/{id_revision}/rechazar", response_model=schemas.RevisionEstimacionPublic)
def rechazar_revision_estimacion(id_revision: int, db: Session = Depends(get_db)):
    return service.RevisionEstimacionService.rechazar(db, id_revision)


@router.get("/{id_estimacion}/revisiones", response_model=List[schemas.RevisionEstimacionPublic])
def consultar_revisiones_estimacion(id_estimacion: int, db: Session = Depends(get_db)):
    return service.RevisionEstimacionService.consultar_por_estimacion(db, id_estimacion)


# --- 5. Facturación Fiscal (CFDI) ---
@router.post("/facturacion", response_model=schemas.FacturacionEstimacionPublic, status_code=status.HTTP_201_CREATED)
def adjuntar_factura_fiscal(factura_in: schemas.FacturacionEstimacionCreate, db: Session = Depends(get_db)):
    return service.FacturacionEstimacionService.adjuntar_fiscal(db, factura_in)


@router.get("/{id_estimacion}/facturacion", response_model=schemas.FacturacionEstimacionPublic)
def consultar_factura_estimacion(id_estimacion: int, db: Session = Depends(get_db)):
    return service.FacturacionEstimacionService.consultar_por_estimacion(db, id_estimacion)