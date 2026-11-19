from typing import List
from fastapi import APIRouter, Depends, Request, status
from sqlmodel import Session, col, select
from app.core.database import get_session
from app.core.dependencies import (
    RequerirRoles,
    get_current_user,
    solo_admin,
    solo_directivo_o_admin,
    solo_residente,
    verificar_participacion_en_obra,
)
from app.models_base import (
    AvancesFisicos,
    ConceptosCatalogo,
    Contratos,
    Polizas,
    Usuarios,
)
from . import models, service

router = APIRouter(
    prefix="/obras-contratos",
    tags=["02. Obras, Contratos, Catálogo de Conceptos, Dashboard Directivo y Finiquito"]
)


# --- 1. Padrón de Empresas Contratistas (3NF) ---
@router.post("/empresas", response_model=models.ContratistaPublic, status_code=status.HTTP_201_CREATED)
def crear_empresa_contratista(
    empresa_in: models.ContratistaCreate,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    return service.ContratistaService.crear(session, empresa_in)


@router.get("/empresas", response_model=List[models.ContratistaPublic])
def listar_empresas_contratistas(
    skip: int = 0,
    limit: int = 100,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(get_current_user)
):
    return service.ContratistaService.consultar(session, skip=skip, limit=limit)


@router.patch("/empresas/{id_contratista}/desactivar", response_model=models.ContratistaPublic)
def desactivar_empresa_contratista(
    id_contratista: int,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    return service.ContratistaService.desactivar(session, id_contratista)


# --- 2. Obras Públicas (RF-ADM-04) ---
@router.post("/obras", response_model=models.ObraPublic, status_code=status.HTTP_201_CREATED)
def crear_obra_publica(
    request: Request,
    obra_in: models.ObraCreate,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    ip = request.client.host if request.client else "127.0.0.1"
    return service.ObraContratoService.crear_obra(session, obra_in, admin, ip)


@router.get("/obras", response_model=List[models.ObraPublic])
def listar_obras(
    skip: int = 0,
    limit: int = 100,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(get_current_user)
):
    return service.ObraContratoService.listar_obras_segun_rol(session, current_user, skip=skip, limit=limit)


@router.get("/obras/{id_obra}", response_model=models.ObraPublic)
def obtener_detalle_obra(
    id_obra: int,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(get_current_user)
):
    verificar_participacion_en_obra(id_obra, session, current_user)
    obra = service.ObraContratoService.obtener_obra(session, id_obra)
    return service.ObraContratoService._enriquecer_obra_public(session, obra)


@router.patch("/obras/{id_obra}", response_model=models.ObraPublic)
def actualizar_obra(
    id_obra: int,
    request: Request,
    obra_in: models.ObraUpdate,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    ip = request.client.host if request.client else "127.0.0.1"
    return service.ObraContratoService.actualizar_obra(session, id_obra, obra_in, admin, ip)


# --- 3. Contratos y Pólizas de Fianza (RF-ADM-04, RF-DIR-03) ---
@router.post("/contratos", response_model=models.ContratoPublic, status_code=status.HTTP_201_CREATED)
def registrar_contrato(
    request: Request,
    contrato_in: models.ContratoCreate,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    ip = request.client.host if request.client else "127.0.0.1"
    return service.ObraContratoService.registrar_contrato(session, contrato_in, admin, ip)


@router.get("/obras/{id_obra}/contratos", response_model=List[models.ContratoPublic])
def consultar_contratos_obra(
    id_obra: int,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(get_current_user)
):
    verificar_participacion_en_obra(id_obra, session, current_user)
    return list(session.exec(select(Contratos).where(Contratos.id_obra == id_obra)).all())


@router.patch("/contratos/{id_contrato}", response_model=models.ContratoPublic)
def actualizar_contrato_en_configuracion(
    id_contrato: int,
    contrato_in: models.ContratoUpdate,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    return service.ObraContratoService.actualizar_contrato(session, id_contrato, contrato_in, admin)


@router.post("/polizas", response_model=models.PolizaPublic, status_code=status.HTTP_201_CREATED)
def registrar_poliza(
    request: Request,
    poliza_in: models.PolizaCreate,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    ip = request.client.host if request.client else "127.0.0.1"
    return service.ObraContratoService.registrar_poliza(session, poliza_in, admin, ip)


@router.patch("/polizas/{id_poliza}", response_model=models.PolizaPublic)
def actualizar_poliza_renovada(
    id_poliza: int,
    poliza_in: models.PolizaUpdate,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    return service.ObraContratoService.actualizar_poliza_renovada(session, id_poliza, poliza_in, admin)


@router.get("/contratos/{id_contrato}/polizas", response_model=List[models.PolizaPublic])
def listar_polizas_contrato(
    id_contrato: int,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(get_current_user)
):
    return list(session.exec(select(Polizas).where(Polizas.id_contrato == id_contrato)).all())


# --- 4. Catálogo de Conceptos y Precios Extraordinarios (RF-SUPT-01, RF-RES-04) ---
@router.post(
    "/conceptos/importar-linea-base",
    response_model=List[models.ConceptoCatalogoPublic],
    status_code=status.HTTP_201_CREATED
)
def importar_conceptos_linea_base(
    conceptos_in: List[models.ConceptoCatalogoCreate],
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(RequerirRoles(["SUPERINTENDENTE", "ADMINISTRADOR"]))
):
    if conceptos_in:
        verificar_participacion_en_obra(conceptos_in[0].id_obra, session, current_user)
    return service.CatalogoConceptosService.cargar_conceptos_ordinarios(session, conceptos_in)


@router.get("/obras/{id_obra}/conceptos", response_model=List[models.ConceptoCatalogoPublic])
def listar_conceptos_obra(
    id_obra: int,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(get_current_user)
):
    verificar_participacion_en_obra(id_obra, session, current_user)
    return list(session.exec(select(ConceptosCatalogo).where(ConceptosCatalogo.id_obra == id_obra)).all())


@router.patch("/conceptos/{id_concepto}", response_model=models.ConceptoCatalogoPublic)
def editar_concepto_antes_de_congelamiento(
    id_concepto: int,
    concepto_in: models.ConceptoCatalogoUpdate,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(RequerirRoles(["SUPERINTENDENTE", "ADMINISTRADOR"]))
):
    conc = session.get(ConceptosCatalogo, id_concepto)
    if conc:
        verificar_participacion_en_obra(conc.id_obra, session, current_user)
    return service.CatalogoConceptosService.editar_concepto_ordinario(session, id_concepto, concepto_in)


@router.post(
    "/conceptos/extraordinarios",
    response_model=models.ConceptoCatalogoPublic,
    status_code=status.HTTP_201_CREATED
)
def inyectar_concepto_extraordinario(
    request: Request,
    inyeccion_in: models.ConceptoExtraordinarioInyeccion,
    session: Session = Depends(get_session),
    residente: Usuarios = Depends(solo_residente)
):
    verificar_participacion_en_obra(inyeccion_in.id_obra, session, residente)
    ip = request.client.host if request.client else "127.0.0.1"
    return service.CatalogoConceptosService.inyectar_concepto_extraordinario(
        session, inyeccion_in, residente, ip
    )


# --- 5. Historial de Avances Físicos, Dashboard Directivo, Reportes y Finiquito ---
@router.get("/obras/{id_obra}/avances-fisicos", response_model=List[models.AvanceFisicoPublic])
def consultar_historial_avances_obra(
    id_obra: int,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(get_current_user)
):
    verificar_participacion_en_obra(id_obra, session, current_user)
    return list(
        session.exec(
            select(AvancesFisicos)
            .where(AvancesFisicos.id_obra == id_obra)
            .order_by(col(AvancesFisicos.id_avance).desc())
        ).all()
    )


@router.get("/directivo/dashboard", response_model=List[models.DashboardObraItem])
def obtener_dashboard_directivo(
    session: Session = Depends(get_session),
    directivo: Usuarios = Depends(solo_directivo_o_admin)
):
    return service.DirectivoFiniquitoService.obtener_dashboard_ejecutivo(session)


@router.get("/directivo/obras/{id_obra}/reporte-financiero", response_model=models.ReporteGerencialFinanciero)
def exportar_reporte_financiero_obra(
    id_obra: int,
    request: Request,
    session: Session = Depends(get_session),
    directivo: Usuarios = Depends(solo_directivo_o_admin)
):
    ip = request.client.host if request.client else "127.0.0.1"
    return service.DirectivoFiniquitoService.exportar_reporte_financiero(session, id_obra, directivo, ip)


@router.post("/obras/{id_obra}/finiquito", response_model=models.ActaFiniquitoResumen)
def emitir_recepcion_fisica_y_finiquito(
    id_obra: int,
    request: Request,
    solicitud: models.FiniquitoSolicitud,
    session: Session = Depends(get_session),
    residente: Usuarios = Depends(solo_residente)
):
    verificar_participacion_en_obra(id_obra, session, residente)
    ip = request.client.host if request.client else "127.0.0.1"
    return service.DirectivoFiniquitoService.generar_recepcion_y_finiquito(
        session, id_obra, solicitud, residente, ip
    )
