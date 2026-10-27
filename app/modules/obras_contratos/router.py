from typing import List
from fastapi import APIRouter, Depends, status
from sqlmodel import Session
from app.core.database import get_session
from app.core.dependencies import (
    solo_admin,
    solo_superintendente,
    RequerirRoles,
    verificar_participacion_en_obra
)
from . import models, service

router = APIRouter(prefix="/obras-contratos", tags=["02. Obras, Contratos, Catálogo e Insumos"])


# --- 1. Empresas Contratistas ---
@router.post("/empresas", response_model=models.EmpresaContratistaPublic, status_code=status.HTTP_201_CREATED)
def crear_empresa(
    empresa_in: models.EmpresaContratistaCreate,
    session: Session = Depends(get_session),
    admin=Depends(solo_admin)
):
    return service.EmpresaContratistaService.crear(session, empresa_in)


@router.get("/empresas", response_model=List[models.EmpresaContratistaPublic])
def listar_empresas(
    skip: int = 0,
    limit: int = 100,
    session: Session = Depends(get_session)
):
    return service.EmpresaContratistaService.consultar(session, skip=skip, limit=limit)


@router.patch("/empresas/{id_empresa}/desactivar", response_model=models.EmpresaContratistaPublic)
def desactivar_empresa(
    id_empresa: int,
    session: Session = Depends(get_session),
    admin=Depends(solo_admin)
):
    return service.EmpresaContratistaService.desactivar(session, id_empresa)


# --- 2. Obras y Avance Físico ---
@router.post("/obras", response_model=models.ObraPublic, status_code=status.HTTP_201_CREATED)
def crear_obra(
    obra_in: models.ObraCreate,
    session: Session = Depends(get_session),
    admin=Depends(solo_admin)
):
    return service.ObraService.crear(session, obra_in)


@router.get("/obras", response_model=List[models.ObraPublic])
def listar_obras(
    skip: int = 0,
    limit: int = 100,
    session: Session = Depends(get_session)
):
    return service.ObraService.consultar(session, skip=skip, limit=limit)


@router.get("/obras/{id_obra}", response_model=models.ObraPublic)
def obtener_obra(
    id_obra: int,
    session: Session = Depends(get_session)
):
    return service.ObraService.obtener_por_id(session, id_obra)


@router.patch("/obras/{id_obra}", response_model=models.ObraPublic)
def actualizar_obra(
    id_obra: int,
    obra_in: models.ObraUpdate,
    session: Session = Depends(get_session),
    admin=Depends(solo_admin)
):
    return service.ObraService.actualizar(session, id_obra, obra_in)


@router.patch("/obras/{id_obra}/cerrar", response_model=models.ObraPublic)
def cerrar_obra(
    id_obra: int,
    session: Session = Depends(get_session),
    admin=Depends(solo_admin)
):
    return service.ObraService.cerrar(session, id_obra)


@router.post("/avances-fisicos", response_model=models.AvanceFisicoPublic, status_code=status.HTTP_201_CREATED)
def registrar_avance_fisico(
    avance_in: models.AvanceFisicoCreate,
    session: Session = Depends(get_session),
    current_user=Depends(RequerirRoles(["RESIDENTE", "SUPERVISOR", "ADMINISTRADOR"]))
):
    verificar_participacion_en_obra(avance_in.id_obra, session, current_user)
    return service.ObraService.registrar_avance_fisico(session, avance_in)


# --- 3. Contratos y Pólizas ---
@router.post("/contratos", response_model=models.ContratoPublic, status_code=status.HTTP_201_CREATED)
def registrar_contrato(
    contrato_in: models.ContratoCreate,
    session: Session = Depends(get_session),
    admin=Depends(solo_admin)
):
    return service.ContratoService.registrar(session, contrato_in)


@router.get("/obras/{id_obra}/contratos", response_model=List[models.ContratoPublic])
def consultar_contratos_obra(
    id_obra: int,
    session: Session = Depends(get_session)
):
    return service.ContratoService.consultar_por_obra(session, id_obra)


@router.patch("/contratos/{id_contrato}/borrador", response_model=models.ContratoPublic)
def actualizar_borrador_contrato(
    id_contrato: int,
    contrato_in: models.ContratoUpdate,
    session: Session = Depends(get_session),
    admin=Depends(solo_admin)
):
    return service.ContratoService.actualizar_borrador(session, id_contrato, contrato_in)


@router.post("/polizas", response_model=models.PolizaPublic, status_code=status.HTTP_201_CREATED)
def registrar_poliza(
    poliza_in: models.PolizaCreate,
    session: Session = Depends(get_session),
    admin=Depends(solo_admin)
):
    return service.ContratoService.registrar_poliza(session, poliza_in)


# --- 4. Insumos y Catálogo de Conceptos ---
@router.post("/insumos", response_model=models.InsumoPublic, status_code=status.HTTP_201_CREATED)
def crear_insumo_obra(
    insumo_in: models.InsumoCreate,
    session: Session = Depends(get_session),
    current_user=Depends(RequerirRoles(["SUPERINTENDENTE", "ADMINISTRADOR"]))
):
    verificar_participacion_en_obra(insumo_in.id_obra, session, current_user)
    return service.CatalogoInsumoService.crear_insumo(session, insumo_in)


@router.get("/obras/{id_obra}/insumos", response_model=List[models.InsumoPublic])
def listar_insumos_obra(
    id_obra: int,
    session: Session = Depends(get_session)
):
    return service.CatalogoInsumoService.consultar_insumos_obra(session, id_obra)


@router.post(
    "/conceptos/importar-linea-base",
    response_model=List[models.ConceptoCatalogoPublic],
    status_code=status.HTTP_201_CREATED
)
def importar_conceptos_linea_base(
    conceptos_in: List[models.ConceptoCatalogoCreate],
    session: Session = Depends(get_session),
    current_user=Depends(RequerirRoles(["SUPERINTENDENTE", "ADMINISTRADOR"]))
):
    if conceptos_in:
        verificar_participacion_en_obra(conceptos_in[0].id_obra, session, current_user)
    return service.CatalogoInsumoService.importar_linea_base(session, conceptos_in)


@router.get("/obras/{id_obra}/conceptos", response_model=List[models.ConceptoCatalogoPublic])
def listar_conceptos_obra(
    id_obra: int,
    session: Session = Depends(get_session)
):
    return service.CatalogoInsumoService.consultar_conceptos_obra(session, id_obra)


@router.patch("/conceptos/{id_concepto}", response_model=models.ConceptoCatalogoPublic)
def editar_concepto_antes_bloqueo(
    id_concepto: int,
    concepto_in: models.ConceptoCatalogoUpdate,
    session: Session = Depends(get_session),
    current_user=Depends(RequerirRoles(["SUPERINTENDENTE", "ADMINISTRADOR"]))
):
    return service.CatalogoInsumoService.editar_antes_del_bloqueo(session, id_concepto, concepto_in)


@router.patch("/conceptos/{id_concepto}/bloquear-precio", response_model=models.ConceptoCatalogoPublic)
def bloquear_precio_concepto(
    id_concepto: int,
    session: Session = Depends(get_session),
    current_user=Depends(RequerirRoles(["RESIDENTE", "ADMINISTRADOR"]))
):
    return service.CatalogoInsumoService.bloquear_precio(session, id_concepto)


@router.post(
    "/conceptos-elementos",
    response_model=models.ConceptoElementoPublic,
    status_code=status.HTTP_201_CREATED
)
def vincular_insumo_a_concepto(
    elemento_in: models.ConceptoElementoCreate,
    session: Session = Depends(get_session),
    current_user=Depends(RequerirRoles(["SUPERINTENDENTE", "ADMINISTRADOR"]))
):
    return service.CatalogoInsumoService.crear_concepto_elemento(session, elemento_in)


@router.patch("/conceptos-elementos/{id_concepto_insumos}", response_model=models.ConceptoElementoPublic)
def actualizar_borrador_elemento(
    id_concepto_insumos: int,
    elemento_in: models.ConceptoElementoUpdate,
    session: Session = Depends(get_session),
    current_user=Depends(RequerirRoles(["SUPERINTENDENTE", "ADMINISTRADOR"]))
):
    return service.CatalogoInsumoService.actualizar_borrador_elemento(session, id_concepto_insumos, elemento_in)


# --- 5. Programa de Ejecución (Gantt) ---
@router.post(
    "/programa-ejecucion",
    response_model=models.ProgramaEjecucionPublic,
    status_code=status.HTTP_201_CREATED
)
def crear_actividad_programa(
    prog_in: models.ProgramaEjecucionCreate,
    session: Session = Depends(get_session),
    current_user=Depends(solo_superintendente)
):
    verificar_participacion_en_obra(prog_in.id_obra, session, current_user)
    return service.ProgramaEjecucionService.crear(session, prog_in)


@router.get("/obras/{id_obra}/gantt", response_model=List[models.ProgramaEjecucionPublic])
def consultar_gantt_obra(
    id_obra: int,
    session: Session = Depends(get_session)
):
    return service.ProgramaEjecucionService.consultar_gantt(session, id_obra)


@router.patch("/programa-ejecucion/{id_actividad}/recalendarizar", response_model=models.ProgramaEjecucionPublic)
def recalendarizar_actividad(
    id_actividad: int,
    prog_in: models.ProgramaEjecucionUpdate,
    session: Session = Depends(get_session),
    current_user=Depends(RequerirRoles(["RESIDENTE", "SUPERVISOR", "ADMINISTRADOR"]))
):
    return service.ProgramaEjecucionService.recalendarizar(session, id_actividad, prog_in)