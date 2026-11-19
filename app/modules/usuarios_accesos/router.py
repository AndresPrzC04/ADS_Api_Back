from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, col, select
from app.core.database import get_session
from app.core.dependencies import (
    get_current_user,
    solo_admin,
    solo_directivo_o_admin,
    verificar_participacion_en_obra,
)
from app.core.security import create_access_token, verify_password
from app.models_base import (
    AuditoriaLogs,
    CatEstatus,
    CatTipoConcepto,
    CatTipoEnsayo,
    CatTipoEstimacion,
    CatTipoNotaBitacora,
    CatTipoPoliza,
    CatUnidadesMedida,
    ObrasAsignaciones,
    RolUsuario,
    Usuarios,
)
from . import models, service

router = APIRouter(
    prefix="/usuarios-accesos",
    tags=["01. Administración: Usuarios, Diccionario de Correos, Asignaciones, Catálogos y Auditoría"]
)


# --- 1. Autenticación OAuth2 / JWT (RNF-SEG-05: 20 minutos) ---
@router.post("/login", response_model=models.TokenResponse)
def login_oauth2(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session)
):
    usuario = session.exec(
        select(Usuarios).where(Usuarios.correo == form_data.username.strip().lower())
    ).first()

    if not usuario or not verify_password(form_data.password, usuario.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo electrónico o contraseña incorrectos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="RN-ADM-01.4: La cuenta de usuario se encuentra suspendida o inhabilitada."
        )

    nombre_rol = usuario.rol.nombre.upper() if usuario.rol else "SIN_ROL"
    access_token = create_access_token(
        data={
            "sub": str(usuario.id_usuario),
            "correo": usuario.correo,
            "rol": nombre_rol
        }
    )

    ip_cliente = request.client.host if request.client else "127.0.0.1"
    service.AuditoriaService.registrar_evento(
        session=session,
        id_usuario=usuario.id_usuario,
        tipo_accion="SEGURIDAD",
        accion_ejecutada="LOGIN_SISTEMA",
        descripcion="Inicio de sesión exitoso mediante OAuth2/JWT",
        ip_origen=ip_cliente
    )

    return models.TokenResponse(
        access_token=access_token,
        id_usuario=usuario.id_usuario,
        nombre_completo=usuario.nombre_completo,
        correo=usuario.correo,
        rol=nombre_rol
    )


@router.get("/mi-perfil", response_model=models.UsuarioPublic)
def obtener_mi_perfil(current_user: Usuarios = Depends(get_current_user)):
    return current_user


# --- 2. Diccionario de Correos y Dominios Autorizados (RN-ADM-01.8 a RN-ADM-01.11) ---
@router.post(
    "/catalogos/correos-autorizados",
    response_model=models.CorreoAutorizadoPublic,
    status_code=status.HTTP_201_CREATED
)
def registrar_correo_o_dominio_autorizado(
    request: Request,
    entrada_in: models.CorreoAutorizadoCreate,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    ip = request.client.host if request.client else "127.0.0.1"
    return service.DiccionarioCorreoService.registrar_entrada(session, entrada_in, admin, ip)


@router.get("/catalogos/correos-autorizados", response_model=List[models.CorreoAutorizadoPublic])
def listar_correos_autorizados(
    id_contratista: Optional[int] = None,
    solo_activos: bool = True,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    return service.DiccionarioCorreoService.listar_entradas(
        session, id_contratista=id_contratista, solo_activos=solo_activos
    )


@router.patch(
    "/catalogos/correos-autorizados/{id_correo_autorizado}/desactivar",
    response_model=models.CorreoAutorizadoPublic
)
def desactivar_correo_autorizado(
    id_correo_autorizado: int,
    request: Request,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    ip = request.client.host if request.client else "127.0.0.1"
    return service.DiccionarioCorreoService.desactivar_entrada(session, id_correo_autorizado, admin, ip)


# --- 3. Gestión de Identidad y Ciclo de Vida (RF-ADM-01 y RF-ADM-02) ---
@router.get("/roles", response_model=List[models.RolUsuarioPublic])
def listar_roles(
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    return list(session.exec(select(RolUsuario).where(col(RolUsuario.activo).is_(True))).all())


@router.post("/usuarios", response_model=models.UsuarioPublic, status_code=status.HTTP_201_CREATED)
def crear_usuario(
    request: Request,
    usuario_in: models.UsuarioCreate,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    ip = request.client.host if request.client else "127.0.0.1"
    return service.UsuarioService.crear(session, usuario_in, admin, ip)


@router.get("/usuarios", response_model=List[models.UsuarioPublic])
def listar_usuarios(
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    return list(session.exec(select(Usuarios).order_by(col(Usuarios.id_usuario).asc())).all())


@router.patch("/usuarios/{id_usuario}", response_model=models.UsuarioPublic)
def modificar_usuario(
    id_usuario: int,
    request: Request,
    usuario_in: models.UsuarioUpdate,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    ip = request.client.host if request.client else "127.0.0.1"
    return service.UsuarioService.modificar(session, id_usuario, usuario_in, admin, ip)


@router.patch("/usuarios/{id_usuario}/suspender")
def suspender_usuario(
    id_usuario: int,
    request: Request,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    ip = request.client.host if request.client else "127.0.0.1"
    return service.UsuarioService.suspender(session, id_usuario, admin, ip)


# --- 4. Asignación de Proyectos y Relevos Operativos (RF-ADM-03) ---
@router.post(
    "/asignaciones",
    response_model=models.ObraAsignacionPublic,
    status_code=status.HTTP_201_CREATED
)
def vincular_usuario_a_obra(
    request: Request,
    asig_in: models.ObraAsignacionCreate,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    ip = request.client.host if request.client else "127.0.0.1"
    return service.AsignacionObraService.asignar_usuario_a_obra(session, asig_in, admin, ip)


@router.patch("/asignaciones/{id_asignacion}/desvincular")
def desvincular_usuario_de_obra(
    id_asignacion: int,
    request: Request,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    ip = request.client.host if request.client else "127.0.0.1"
    return service.AsignacionObraService.desvincular_usuario_de_obra(session, id_asignacion, admin, ip)


@router.post("/relevos")
def ejecutar_relevo_en_obra(
    request: Request,
    relevo_in: models.RelevoOperativoCreate,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    ip = request.client.host if request.client else "127.0.0.1"
    return service.AsignacionObraService.ejecutar_relevo_operativo(session, relevo_in, admin, ip)


@router.get("/obras/{id_obra}/asignaciones", response_model=List[models.ObraAsignacionPublic])
def listar_asignaciones_por_obra(
    id_obra: int,
    session: Session = Depends(get_session),
    current_user: Usuarios = Depends(get_current_user)
):
    verificar_participacion_en_obra(id_obra, session, current_user)
    return list(
        session.exec(
            select(ObrasAsignaciones)
            .where(ObrasAsignaciones.id_obra == id_obra)
            .order_by(col(ObrasAsignaciones.id_asignacion).desc())
        ).all()
    )


# --- 5. Catálogos Maestros Institucionales en 3NF (RF-ADM-05 y RN-ADM-05.1) ---
@router.get("/catalogos/unidades-medida", response_model=List[models.UnidadMedidaPublic])
def listar_unidades_medida(session: Session = Depends(get_session)):
    return list(session.exec(select(CatUnidadesMedida).where(col(CatUnidadesMedida.activo).is_(True))).all())


@router.post(
    "/catalogos/unidades-medida",
    response_model=models.UnidadMedidaPublic,
    status_code=status.HTTP_201_CREATED
)
def crear_unidad_medida(
    unidad_in: models.UnidadMedidaCreate,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    nueva = CatUnidadesMedida(clave=unidad_in.clave.upper(), nombre=unidad_in.nombre, activo=True)
    session.add(nueva)
    session.commit()
    session.refresh(nueva)
    return nueva


@router.patch("/catalogos/unidades-medida/{id_unidad}/desactivar", response_model=models.UnidadMedidaPublic)
def desactivar_unidad_medida(
    id_unidad: int,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    unidad = session.get(CatUnidadesMedida, id_unidad)
    if not unidad:
        raise HTTPException(status_code=404, detail="Unidad de medida no encontrada.")
    unidad.activo = False
    session.add(unidad)
    session.commit()
    session.refresh(unidad)
    return unidad


@router.get("/catalogos/tipos-concepto", response_model=List[models.TipoConceptoPublic])
def listar_tipos_concepto(session: Session = Depends(get_session)):
    return list(session.exec(select(CatTipoConcepto).where(col(CatTipoConcepto.activo).is_(True))).all())


@router.post(
    "/catalogos/tipos-concepto",
    response_model=models.TipoConceptoPublic,
    status_code=status.HTTP_201_CREATED
)
def crear_tipo_concepto(
    tipo_in: models.TipoConceptoCreate,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    nuevo = CatTipoConcepto(
        clave=tipo_in.clave.upper(),
        nombre=tipo_in.nombre,
        requiere_apu=tipo_in.requiere_apu,
        activo=True
    )
    session.add(nuevo)
    session.commit()
    session.refresh(nuevo)
    return nuevo


@router.patch("/catalogos/tipos-concepto/{id_tipo_concepto}/desactivar", response_model=models.TipoConceptoPublic)
def desactivar_tipo_concepto(
    id_tipo_concepto: int,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    item = session.get(CatTipoConcepto, id_tipo_concepto)
    if not item:
        raise HTTPException(status_code=404, detail="Tipo de concepto no encontrado.")
    item.activo = False
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.get("/catalogos/tipos-estimacion", response_model=List[models.TipoEstimacionPublic])
def listar_tipos_estimacion(session: Session = Depends(get_session)):
    return list(session.exec(select(CatTipoEstimacion).where(col(CatTipoEstimacion.activo).is_(True))).all())


@router.post(
    "/catalogos/tipos-estimacion",
    response_model=models.TipoEstimacionPublic,
    status_code=status.HTTP_201_CREATED
)
def crear_tipo_estimacion(
    tipo_in: models.TipoEstimacionCreate,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    nuevo = CatTipoEstimacion(
        clave=tipo_in.clave.upper(),
        nombre=tipo_in.nombre,
        descripcion=tipo_in.descripcion,
        activo=True
    )
    session.add(nuevo)
    session.commit()
    session.refresh(nuevo)
    return nuevo


@router.patch("/catalogos/tipos-estimacion/{id_tipo_estimacion}/desactivar", response_model=models.TipoEstimacionPublic)
def desactivar_tipo_estimacion(
    id_tipo_estimacion: int,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    item = session.get(CatTipoEstimacion, id_tipo_estimacion)
    if not item:
        raise HTTPException(status_code=404, detail="Tipo de estimación no encontrado.")
    item.activo = False
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.get("/catalogos/tipos-poliza", response_model=List[models.TipoPolizaPublic])
def listar_tipos_poliza(session: Session = Depends(get_session)):
    return list(session.exec(select(CatTipoPoliza).where(col(CatTipoPoliza.activo).is_(True))).all())


@router.post(
    "/catalogos/tipos-poliza",
    response_model=models.TipoPolizaPublic,
    status_code=status.HTTP_201_CREATED
)
def crear_tipo_poliza(
    tipo_in: models.TipoPolizaCreate,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    nuevo = CatTipoPoliza(clave=tipo_in.clave.upper(), nombre=tipo_in.nombre, activo=True)
    session.add(nuevo)
    session.commit()
    session.refresh(nuevo)
    return nuevo


@router.patch("/catalogos/tipos-poliza/{id_tipo_poliza}/desactivar", response_model=models.TipoPolizaPublic)
def desactivar_tipo_poliza(
    id_tipo_poliza: int,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    item = session.get(CatTipoPoliza, id_tipo_poliza)
    if not item:
        raise HTTPException(status_code=404, detail="Tipo de póliza no encontrado.")
    item.activo = False
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.get("/catalogos/estatus", response_model=List[models.EstatusPublic])
def listar_estatus_institucionales(
    ambito: Optional[str] = None,
    session: Session = Depends(get_session)
):
    stmt = select(CatEstatus).where(col(CatEstatus.activo).is_(True))
    if ambito:
        stmt = stmt.where(CatEstatus.ambito == ambito.upper())
    return list(session.exec(stmt).all())


@router.post(
    "/catalogos/estatus",
    response_model=models.EstatusPublic,
    status_code=status.HTTP_201_CREATED
)
def crear_estatus_institucional(
    est_in: models.EstatusCreate,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    nuevo = CatEstatus(
        ambito=est_in.ambito.upper(),
        clave=est_in.clave.upper(),
        nombre=est_in.nombre,
        activo=True
    )
    session.add(nuevo)
    session.commit()
    session.refresh(nuevo)
    return nuevo


@router.patch("/catalogos/estatus/{id_estatus}/desactivar", response_model=models.EstatusPublic)
def desactivar_estatus_institucional(
    id_estatus: int,
    session: Session = Depends(get_session),
    admin: Usuarios = Depends(solo_admin)
):
    item = session.get(CatEstatus, id_estatus)
    if not item:
        raise HTTPException(status_code=404, detail="Estatus no encontrado.")
    item.activo = False
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.get("/catalogos/tipos-nota-bitacora", response_model=List[models.TipoNotaBitacoraPublic])
def listar_tipos_nota_bitacora(session: Session = Depends(get_session)):
    return list(session.exec(select(CatTipoNotaBitacora).where(col(CatTipoNotaBitacora.activo).is_(True))).all())


@router.get("/catalogos/tipos-ensayo", response_model=List[models.TipoEnsayoPublic])
def listar_tipos_ensayo(session: Session = Depends(get_session)):
    return list(session.exec(select(CatTipoEnsayo).where(col(CatTipoEnsayo.activo).is_(True))).all())


# --- 6. Consulta de Auditoría (RNF-SEG-03) ---
@router.get("/auditoria", response_model=List[models.AuditoriaLogPublic])
def consultar_bitacora_auditoria(
    skip: int = 0,
    limit: int = 50,
    session: Session = Depends(get_session),
    autorizado: Usuarios = Depends(solo_directivo_o_admin)
):
    return list(
        session.exec(
            select(AuditoriaLogs)
            .order_by(col(AuditoriaLogs.fecha_inicio).desc())
            .offset(skip)
            .limit(limit)
        ).all()
    )
