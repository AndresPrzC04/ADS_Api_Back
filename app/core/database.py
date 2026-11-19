import os
from typing import Generator
from sqlmodel import SQLModel, Session, create_engine, select

# app/core/database.py
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:boleta2020020444@localhost:5432/obras"
)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)


def init_db() -> None:
    """Crea todas las tablas declaradas en SQLModel e inicializa los catálogos base."""
    import app.models_base  # noqa: F401
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        seed_catalogos_base(session)


def get_session() -> Generator[Session, None, None]:
    """Inyección de dependencias para proveer la sesión de base de datos."""
    with Session(engine) as session:
        yield session


def seed_catalogos_base(session: Session) -> None:
    """
    Inicializa los 5 roles base (RF-ADM-02), el dominio institucional base en
    Cat_Correos_Autorizados (RN-ADM-01.8) y los catálogos maestros (RF-ADM-05).
    """
    from app.models_base import (
        CatCorreosAutorizados,
        CatEstatus,
        CatTipoConcepto,
        CatTipoEnsayo,
        CatTipoEstimacion,
        CatTipoNotaBitacora,
        CatTipoPoliza,
        CatUnidadesMedida,
        RolUsuario,
    )

    roles_base = [
        ("ADMINISTRADOR", "Gestión de identidad, diccionario de correos, obras, contratos, pólizas y relevos"),
        ("DIRECTIVO", "Consulta ejecutiva global de tableros y reportes financieros en solo lectura"),
        ("RESIDENTE", "Representante gubernamental: apertura/cierre de bitácora, APU, autorización de pagos y finiquito"),
        ("SUPERVISOR", "Reportes de supervisión con avance físico, dictamen de estimaciones y control de calidad"),
        ("SUPERINTENDENTE", "Representante del contratista: catálogo base, estimaciones, bitácora y CFDI"),
    ]
    mapa_roles = {}
    for nombre, desc in roles_base:
        rol = session.exec(select(RolUsuario).where(RolUsuario.nombre == nombre)).first()
        if not rol:
            rol = RolUsuario(nombre=nombre, descripcion=desc, activo=True)
            session.add(rol)
            session.flush()
        mapa_roles[nombre] = rol.id_rol_usuario

    # Dominio institucional base por defecto (RN-ADM-01.8)
    dominios_institucionales = ["gob.mx", "obraspublicas.gob.mx"]
    for dom in dominios_institucionales:
        if not session.exec(
            select(CatCorreosAutorizados).where(CatCorreosAutorizados.valor == dom)
        ).first():
            session.add(
                CatCorreosAutorizados(
                    id_contratista=None,
                    tipo_registro="DOMINIO",
                    valor=dom,
                    activo=True
                )
            )

    estatus_base = [
        # Ámbito OBRA
        ("OBRA", "EN_CONFIGURACION", "En Configuración Inicial"),
        ("OBRA", "EN_EJECUCION", "En Ejecución"),
        ("OBRA", "ALERTA_VACANTE_OPERATIVA", "Alerta de Vacante Operativa"),
        ("OBRA", "SUSPENDIDA", "Suspendida Temporalmente"),
        ("OBRA", "FINIQUITADA", "Finiquitada / Cerrada"),
        ("OBRA", "CERRADA", "Cerrada"),
        # Ámbito CONTRATO
        ("CONTRATO", "VIGENTE", "Contrato Vigente"),
        ("CONTRATO", "SUSPENDIDO", "Contrato Suspendido"),
        ("CONTRATO", "FINIQUITADO", "Contrato Finiquitado / Cerrado"),
        # Ámbito ESTIMACION
        ("ESTIMACION", "BORRADOR", "Borrador en Captura"),
        ("ESTIMACION", "EN_REVISION", "En Revisión por Supervisión"),
        ("ESTIMACION", "OBSERVADA", "Observada / Rechazada para Subsanación"),
        ("ESTIMACION", "RECHAZADA", "Rechazada para Subsanación"),
        ("ESTIMACION", "APROBADA", "Aprobada Técnicamente por Supervisor"),
        ("ESTIMACION", "AUTORIZADA_PAGO", "Autorizada para Pago por Residente"),
        ("ESTIMACION", "LIQUIDADA", "Estimación Liquidada / Pagada"),
        # Ámbito REVISION
        ("REVISION", "PENDIENTE", "Pendiente de Dictamen"),
        ("REVISION", "APROBADA", "Dictamen Técnico Aprobado"),
        ("REVISION", "RECHAZADA", "Dictamen Técnico Rechazado"),
        # Ámbito PAGO
        ("PAGO", "LIQUIDADA", "Pago Efectivamente Liquidado"),
        # Ámbito CALIDAD
        ("CALIDAD", "APROBADO", "Ensayo de Laboratorio Aprobado"),
        ("CALIDAD", "RECHAZADO", "Ensayo de Laboratorio Rechazado"),
    ]
    for ambito, clave, nombre in estatus_base:
        existe = session.exec(
            select(CatEstatus).where(CatEstatus.ambito == ambito, CatEstatus.clave == clave)
        ).first()
        if not existe:
            session.add(CatEstatus(ambito=ambito, clave=clave, nombre=nombre, activo=True))

    unidades_base = [
        ("M2", "Metro Cuadrado"),
        ("M3", "Metro Cúbico"),
        ("ML", "Metro Lineal"),
        ("KG", "Kilogramo"),
        ("TON", "Tonelada"),
        ("PZA", "Pieza"),
        ("LOTE", "Lote"),
    ]
    for clave, nombre in unidades_base:
        if not session.exec(select(CatUnidadesMedida).where(CatUnidadesMedida.clave == clave)).first():
            session.add(CatUnidadesMedida(clave=clave, nombre=nombre, activo=True))

    tipos_concepto = [
        ("ORDINARIO", "Concepto de Catálogo Original", False),
        ("EXTRAORDINARIO", "Concepto Extraordinario Fuera de Catálogo", True),
    ]
    for clave, nombre, req_apu in tipos_concepto:
        if not session.exec(select(CatTipoConcepto).where(CatTipoConcepto.clave == clave)).first():
            session.add(CatTipoConcepto(clave=clave, nombre=nombre, requiere_apu=req_apu, activo=True))

    tipos_estimacion = [
        ("ORDINARIA", "Estimación Ordinaria de Trabajos Ejecutados"),
        ("CANTIDADES_ADICIONALES", "Estimación de Volúmenes o Cantidades Adicionales"),
        ("EXTRAORDINARIA", "Estimación de Conceptos Extraordinarios Autorizados"),
    ]
    for clave, nombre in tipos_estimacion:
        if not session.exec(select(CatTipoEstimacion).where(CatTipoEstimacion.clave == clave)).first():
            session.add(CatTipoEstimacion(clave=clave, nombre=nombre, descripcion=nombre, activo=True))

    tipos_poliza = [
        ("ANTICIPO", "Póliza de Fianza de Anticipo"),
        ("CUMPLIMIENTO", "Póliza de Fianza de Cumplimiento"),
        ("VICIOS_OCULTOS", "Póliza de Fianza de Vicios Ocultos"),
    ]
    for clave, nombre in tipos_poliza:
        if not session.exec(select(CatTipoPoliza).where(CatTipoPoliza.clave == clave)).first():
            session.add(CatTipoPoliza(clave=clave, nombre=nombre, activo=True))

    id_res = mapa_roles.get("RESIDENTE")
    id_sup = mapa_roles.get("SUPERVISOR")
    id_supt = mapa_roles.get("SUPERINTENDENTE")
    tipos_nota = [
        ("APERTURA", "Nota de Apertura de Bitácora", id_res, 0),
        ("ORDEN_TRABAJO", "Orden Técnica de Trabajo", id_res, 0),
        ("AUTORIZACION_ADICIONALES", "Autorización de Cantidades Adicionales", id_res, 0),
        ("SUSPENSION_TEMPORAL", "Notificación de Suspensión Temporal de Obra", id_res, 0),
        ("REANUDACION", "Notificación de Reanudación de Obra", id_res, 0),
        ("CIERRE", "Nota de Cierre Definitivo de Bitácora", id_res, 0),
        ("SOLICITUD", "Solicitud de Autorización en Bitácora", id_supt, 0),
        ("INCIDENTE_OPERATIVO", "Registro de Incidente Operativo", id_supt, 0),
        ("RESPUESTA", "Nota de Respuesta del Contratista", id_supt, 0),
        ("AVISO_TERMINACION", "Aviso de Terminación de los Trabajos", id_supt, 6),
        ("SEGUIMIENTO", "Nota de Seguimiento de Avance Físico", id_sup, 0),
        ("INCIDENCIA_CAMPO", "Incidencia Detectada en Campo", id_sup, 0),
        ("ACUERDO_JUNTA", "Acuerdo Tomado en Junta de Trabajo", id_sup, 0),
        ("DICTAMEN_CALIDAD", "Dictamen de Control de Calidad", id_sup, 0),
    ]
    for clave, nombre, id_rol_exc, min_img in tipos_nota:
        if not session.exec(select(CatTipoNotaBitacora).where(CatTipoNotaBitacora.clave == clave)).first():
            session.add(
                CatTipoNotaBitacora(
                    clave=clave,
                    nombre=nombre,
                    id_rol_exclusivo=id_rol_exc,
                    min_imagenes=min_img,
                    activo=True
                )
            )

    ensayos_base = [
        ("PROCTOR", "Prueba de Compactación Proctor Estándar", "NMX-C-416-ONNCCE"),
        ("COMPRESION_CONCRETO", "Resistencia a la Compresión Simple de Cilindros de Concreto", "NMX-C-083-ONNCCE"),
        ("REVENIMIENTO", "Determinación del Revenimiento en el Concreto Fresco", "NMX-C-156-ONNCCE"),
    ]
    for clave, nombre, norma in ensayos_base:
        if not session.exec(select(CatTipoEnsayo).where(CatTipoEnsayo.clave == clave)).first():
            session.add(
                CatTipoEnsayo(clave=clave, nombre=nombre, norma_referencia=norma, activo=True)
            )

    session.commit()
