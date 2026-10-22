from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from . import schemas, service

router = APIRouter(prefix="/obras-contratos", tags=["02. Obras, Contratos, Catálogo e Insumos"])


# --- 1. Empresas Contratistas ---
@router.post("/empresas", response_model=schemas.EmpresaContratistaPublic, status_code=status.HTTP_201_CREATED)
def crear_empresa(empresa_in: schemas.EmpresaContratistaCreate, db: Session = Depends(get_db)):
    return service.EmpresaContratistaService.crear(db, empresa_in)


@router.get("/empresas", response_model=List[schemas.EmpresaContratistaPublic])
def listar_empresas(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return service.EmpresaContratistaService.consultar(db, skip=skip, limit=limit)


@router.patch("/empresas/{id_empresa}/desactivar", response_model=schemas.EmpresaContratistaPublic)
def desactivar_empresa(id_empresa: int, db: Session = Depends(get_db)):
    return service.EmpresaContratistaService.desactivar(db, id_empresa)


# --- 2. Obras y Avance Físico ---
@router.post("/obras", response_model=schemas.ObraPublic, status_code=status.HTTP_201_CREATED)
def crear_obra(obra_in: schemas.ObraCreate, db: Session = Depends(get_db)):
    return service.ObraService.crear(db, obra_in)


@router.get("/obras", response_model=List[schemas.ObraPublic])
def listar_obras(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return service.ObraService.consultar(db, skip=skip, limit=limit)


@router.patch("/obras/{id_obra}", response_model=schemas.ObraPublic)
def actualizar_obra(id_obra: int, obra_in: schemas.ObraUpdate, db: Session = Depends(get_db)):
    return service.ObraService.actualizar(db, id_obra, obra_in)


@router.patch("/obras/{id_obra}/cerrar", response_model=schemas.ObraPublic)
def cerrar_obra(id_obra: int, db: Session = Depends(get_db)):
    return service.ObraService.cerrar(db, id_obra)


@router.post("/avances-fisicos", response_model=schemas.AvanceFisicoPublic, status_code=status.HTTP_201_CREATED)
def registrar_avance_fisico(avance_in: schemas.AvanceFisicoCreate, db: Session = Depends(get_db)):
    return service.ObraService.registrar_avance_fisico(db, avance_in)


# --- 3. Contratos y Pólizas ---
@router.post("/contratos", response_model=schemas.ContratoPublic, status_code=status.HTTP_201_CREATED)
def registrar_contrato(contrato_in: schemas.ContratoCreate, db: Session = Depends(get_db)):
    return service.ContratoService.registrar(db, contrato_in)


@router.get("/obras/{id_obra}/contratos", response_model=List[schemas.ContratoPublic])
def consultar_contratos_obra(id_obra: int, db: Session = Depends(get_db)):
    return service.ContratoService.consultar_por_obra(db, id_obra)


@router.patch("/contratos/{id_contrato}/borrador", response_model=schemas.ContratoPublic)
def actualizar_borrador_contrato(id_contrato: int, contrato_in: schemas.ContratoUpdate, db: Session = Depends(get_db)):
    return service.ContratoService.actualizar_borrador(db, id_contrato, contrato_in)


@router.post("/polizas", response_model=schemas.PolizaPublic, status_code=status.HTTP_201_CREATED)
def registrar_poliza(poliza_in: schemas.PolizaCreate, db: Session = Depends(get_db)):
    return service.ContratoService.registrar_poliza(db, poliza_in)


# --- 4. Insumos, Catálogo de Conceptos y Desglose (ConceptoElemento) ---
@router.post("/insumos", response_model=schemas.InsumoPublic, status_code=status.HTTP_201_CREATED)
def crear_insumo_obra(insumo_in: schemas.InsumoCreate, db: Session = Depends(get_db)):
    return service.CatalogoInsumoService.crear_insumo(db, insumo_in)


@router.get("/obras/{id_obra}/insumos", response_model=List[schemas.InsumoPublic])
def listar_insumos_obra(id_obra: int, db: Session = Depends(get_db)):
    return service.CatalogoInsumoService.consultar_insumos_obra(db, id_obra)


@router.post("/conceptos/importar-linea-base", response_model=List[schemas.ConceptoCatalogoPublic], status_code=status.HTTP_201_CREATED)
def importar_conceptos_linea_base(conceptos_in: List[schemas.ConceptoCatalogoCreate], db: Session = Depends(get_db)):
    return service.CatalogoInsumoService.importar_linea_base(db, conceptos_in)


@router.get("/obras/{id_obra}/conceptos", response_model=List[schemas.ConceptoCatalogoPublic])
def listar_conceptos_obra(id_obra: int, db: Session = Depends(get_db)):
    return service.CatalogoInsumoService.consultar_conceptos_obra(db, id_obra)


@router.patch("/conceptos/{id_concepto}", response_model=schemas.ConceptoCatalogoPublic)
def editar_concepto_antes_bloqueo(
    id_concepto: int, concepto_in: schemas.ConceptoCatalogoUpdate, db: Session = Depends(get_db)
):
    return service.CatalogoInsumoService.editar_antes_del_bloqueo(db, id_concepto, concepto_in)


@router.patch("/conceptos/{id_concepto}/bloquear-precio", response_model=schemas.ConceptoCatalogoPublic)
def bloquear_precio_concepto(id_concepto: int, db: Session = Depends(get_db)):
    return service.CatalogoInsumoService.bloquear_precio(db, id_concepto)


@router.post("/conceptos-elementos", response_model=schemas.ConceptoElementoPublic, status_code=status.HTTP_201_CREATED)
def vincular_insumo_a_concepto(elemento_in: schemas.ConceptoElementoCreate, db: Session = Depends(get_db)):
    return service.CatalogoInsumoService.crear_concepto_elemento(db, elemento_in)


@router.patch("/conceptos-elementos/{id_concepto_insumos}", response_model=schemas.ConceptoElementoPublic)
def actualizar_borrador_elemento(
    id_concepto_insumos: int, elemento_in: schemas.ConceptoElementoUpdate, db: Session = Depends(get_db)
):
    return service.CatalogoInsumoService.actualizar_borrador_elemento(db, id_concepto_insumos, elemento_in)


# --- 5. Programa de Ejecución (Gantt) ---
@router.post("/programa-ejecucion", response_model=schemas.ProgramaEjecucionPublic, status_code=status.HTTP_201_CREATED)
def crear_actividad_programa(prog_in: schemas.ProgramaEjecucionCreate, db: Session = Depends(get_db)):
    return service.ProgramaEjecucionService.crear(db, prog_in)


@router.get("/obras/{id_obra}/gantt", response_model=List[schemas.ProgramaEjecucionPublic])
def consultar_gantt_obra(id_obra: int, db: Session = Depends(get_db)):
    return service.ProgramaEjecucionService.consultar_gantt(db, id_obra)


@router.patch("/programa-ejecucion/{id_actividad}/recalendarizar", response_model=schemas.ProgramaEjecucionPublic)
def recalendarizar_actividad(
    id_actividad: int, prog_in: schemas.ProgramaEjecucionUpdate, db: Session = Depends(get_db)
):
    return service.ProgramaEjecucionService.recalendarizar(db, id_actividad, prog_in)