from decimal import Decimal
from sqlmodel import Session, select
from app.core.database import engine, init_db
from app.core.security import get_password_hash
from app.models_base import Usuarios

def seed_catalogos_base(session: Session) -> None:
    """
    Inicializa los 5 roles base (RF-ADM-02), el dominio institucional base en
    Cat_Correos_Autorizados (RN-ADM-01.8) y los catálogos maestros (RF-ADM-05).
    """
    from app.models_base import (
        CatConceptosMaestro,
        CatCorreosAutorizados,
        CatEstatus,
        CatPartidas,
        CatSubpartidas,
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
        # Ámbito REPORTE
        ("REPORTE", "BORRADOR", "Reporte en Borrador"),
        ("REPORTE", "ENVIADO", "Reporte Enviado"),
        ("REPORTE", "FIRMADO", "Reporte Firmado Electrónicamente"),
        # Ámbito INCIDENTE
        ("INCIDENTE", "CREADO", "Incidente Creado"),
        ("INCIDENTE", "EMITIDO", "Incidente Emitido"),
        ("INCIDENTE", "ATENDIDO", "Incidente Atendido"),
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
    mapa_unidades: dict[str, int] = {}
    for clave, nombre in unidades_base:
        unidad = session.exec(select(CatUnidadesMedida).where(CatUnidadesMedida.clave == clave)).first()
        if not unidad:
            unidad = CatUnidadesMedida(clave=clave, nombre=nombre, activo=True)
            session.add(unidad)
            session.flush()
        mapa_unidades[clave] = unidad.id_unidad

    # Precarga idempotente de 3 conceptos de ejemplo en Cat_Conceptos_Maestro (para pruebas de upsert Excel)
    conceptos_maestro_base = [
        (
            "E01-041",
            "Cimentación para edificio de cuatro niveles",
            "Cimentación",
            "Cimentación y desplante",
            "M2",
            Decimal("2231.26"),
        ),
        (
            "E02-015",
            "Concreto hidráulico f'c=250 kg/cm² en columnas y trabes",
            "Estructura",
            "Columnas y trabes de concreto",
            "M3",
            Decimal("3450.00"),
        ),
        (
            "A01-010",
            "Muro de tabique rojo recocido de 14 cm de espesor asentado con mortero cemento-arena",
            "Albañilería",
            "Muros de tabique",
            "M2",
            Decimal("485.50"),
        ),
    ]
    for clave_c, desc_c, nom_part, nom_sub, clave_uni, precio_ref in conceptos_maestro_base:
        partida = session.exec(select(CatPartidas).where(CatPartidas.nombre == nom_part)).first()
        if not partida:
            partida = CatPartidas(nombre=nom_part, activo=True)
            session.add(partida)
            session.flush()

        subpartida = session.exec(
            select(CatSubpartidas).where(
                CatSubpartidas.id_partida == partida.id_partida,
                CatSubpartidas.nombre == nom_sub,
            )
        ).first()
        if not subpartida:
            subpartida = CatSubpartidas(
                id_partida=partida.id_partida,
                nombre=nom_sub,
                activo=True,
            )
            session.add(subpartida)
            session.flush()

        existe_cm = session.exec(
            select(CatConceptosMaestro).where(CatConceptosMaestro.clave_concepto == clave_c)
        ).first()
        if not existe_cm:
            session.add(
                CatConceptosMaestro(
                    id_subpartida=subpartida.id_subpartida,
                    id_unidad=mapa_unidades[clave_uni],
                    clave_concepto=clave_c,
                    descripcion=desc_c,
                    precio_referencia=precio_ref,
                    activo=True,
                )
            )

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

    if not session.exec(select(Usuarios).where(Usuarios.correo == "admin@obraspublicas.gob.mx")).first():
        session.add(
            Usuarios(
                id_rol_usuario=mapa_roles["ADMINISTRADOR"],
                nombre_completo="Administrador Titular",
                correo="admin@obraspublicas.gob.mx",
                password_hash=get_password_hash("Admin1234!"),
                firma_electronica=get_password_hash("FIRMA-ADMIN-01"),
                activo=True,
            )
        )

    session.commit()


def run_seed() -> None:
    init_db()
    with Session(engine) as session:
        seed_catalogos_base(session)
    print("Catálogos base inicializados correctamente.")


if __name__ == "__main__":
    run_seed()