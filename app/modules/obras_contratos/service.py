from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional
from fastapi import HTTPException, status
from sqlmodel import Session, col, func, or_, select
from app.core.security import (
    validar_firma_electronica_y_generar_sello,
    validar_formato_y_tamano_archivo,
)
from app.models_base import (
    AvancesFisicos,
    BitacoraNotas,
    CatEstatus,
    CatTipoConcepto,
    CatTipoEstimacion,
    CatTipoNotaBitacora,
    CatTipoPoliza,
    CatUnidadesMedida,
    ConceptosCatalogo,
    Contratistas,
    Contratos,
    Estimaciones,
    EstimacionesPagadas,
    EvidenciaAdjunta,
    Generadores,
    GeneradoresValidacion,
    Obras,
    ObrasAsignaciones,
    Polizas,
    ProgramaEjecucion,
    RevisionEstimaciones,
    Usuarios,
)
from app.modules.usuario_accesos.service import AsignacionObraService, AuditoriaService
from . import models


def _redondear_2(valor: Decimal) -> Decimal:
    return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ==========================================
# 1. SERVICIO: EMPRESAS CONTRATISTAS (3NF)
# ==========================================
class ContratistaService:
    @staticmethod
    def crear(session: Session, contratista_in: models.ContratistaCreate) -> Contratistas:
        rfc_upper = contratista_in.rfc.strip().upper()
        existente = session.exec(
            select(Contratistas).where(Contratistas.rfc == rfc_upper)
        ).first()
        if existente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe una empresa contratista registrada con este RFC."
            )
        nuevo = Contratistas(
            rfc=rfc_upper,
            razon_social=contratista_in.razon_social,
            activo=True
        )
        session.add(nuevo)
        session.commit()
        session.refresh(nuevo)
        return nuevo

    @staticmethod
    def consultar(session: Session, skip: int = 0, limit: int = 100) -> List[Contratistas]:
        return list(session.exec(select(Contratistas).offset(skip).limit(limit)).all())

    @staticmethod
    def desactivar(session: Session, id_contratista: int) -> Contratistas:
        contratista = session.get(Contratistas, id_contratista)
        if not contratista:
            raise HTTPException(status_code=404, detail="Empresa contratista no encontrada.")
        contratista.activo = False
        session.add(contratista)
        session.commit()
        session.refresh(contratista)
        return contratista


# ==========================================
# 2. SERVICIO: OBRAS PÚBLICAS, CONTRATOS Y PÓLIZAS (RF-ADM-04)
# ==========================================
class ObraContratoService:
    @staticmethod
    def linea_base_congelada(session: Session, id_obra: int) -> bool:
        """
        RN-ADM-04.4 y RN-ADM-04.5: La línea base queda congelada en el instante en que el Residente
        firma la Nota de Apertura de Bitácora (consecutivo 1) o existe al menos una estimación registrada.
        """
        tipo_apertura = session.exec(
            select(CatTipoNotaBitacora).where(CatTipoNotaBitacora.clave == "APERTURA")
        ).first()
        if tipo_apertura:
            nota_apertura_firmada = session.exec(
                select(BitacoraNotas).where(
                    BitacoraNotas.id_obra == id_obra,
                    BitacoraNotas.id_tipo_nota == tipo_apertura.id_tipo_nota,
                    col(BitacoraNotas.firmada).is_(True)
                )
            ).first()
            if nota_apertura_firmada:
                return True

        tiene_estimacion = session.exec(
            select(Estimaciones).where(Estimaciones.id_obra == id_obra)
        ).first()
        return tiene_estimacion is not None

    @staticmethod
    def _enriquecer_obra_public(session: Session, obra: Obras) -> models.ObraPublic:
        est = session.get(CatEstatus, obra.id_estatus)
        return models.ObraPublic(
            id_obra=obra.id_obra,
            id_estatus=obra.id_estatus,
            clave_estatus=est.clave if est else None,
            nombre_obra=obra.nombre_obra,
            presupuesto_total=obra.presupuesto_total,
            fecha_inicio=obra.fecha_inicio,
            fecha_fin=obra.fecha_fin
        )

    @staticmethod
    def crear_obra(
        session: Session, obra_in: models.ObraCreate, admin: Usuarios, ip_origen: str
    ) -> models.ObraPublic:
        if obra_in.fecha_fin < obra_in.fecha_inicio:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La fecha de término no puede ser anterior a la fecha de inicio."
            )

        # RN-ADM-04.1: Al crearse sin personal completo, su estado general inicia en EN_CONFIGURACION
        est_config = session.exec(
            select(CatEstatus).where(
                CatEstatus.ambito == "OBRA",
                CatEstatus.clave == "EN_CONFIGURACION"
            )
        ).first()
        if not est_config:
            raise HTTPException(status_code=500, detail="Catálogo de estatus EN_CONFIGURACION no inicializado.")

        nueva_obra = Obras(
            id_estatus=est_config.id_estatus,
            nombre_obra=obra_in.nombre_obra,
            presupuesto_total=obra_in.presupuesto_total,
            fecha_inicio=obra_in.fecha_inicio,
            fecha_fin=obra_in.fecha_fin
        )
        session.add(nueva_obra)
        session.commit()
        session.refresh(nueva_obra)

        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=admin.id_usuario,
            id_obra=nueva_obra.id_obra,
            tipo_accion="CREACION",
            accion_ejecutada="ALTA_OBRA_PUBLICA",
            descripcion=f"Registro inicial de obra '{nueva_obra.nombre_obra}' en EN_CONFIGURACION",
            ip_origen=ip_origen
        )
        return ObraContratoService._enriquecer_obra_public(session, nueva_obra)

    @staticmethod
    def listar_obras_segun_rol(
        session: Session, current_user: Usuarios, skip: int = 0, limit: int = 100
    ) -> List[models.ObraPublic]:
        """
        RN-ADM-03.1 y RN-DIR-01.1: Administrador y Directivo tienen visibilidad global.
        Residente, Supervisor y Superintendente solo ven obras con asignación vigente.
        """
        rol_nombre = current_user.rol.nombre.upper() if current_user.rol else ""
        if rol_nombre in {"ADMINISTRADOR", "DIRECTIVO"}:
            obras = list(session.exec(select(Obras).offset(skip).limit(limit)).all())
        else:
            hoy = date.today()
            obras = list(
                session.exec(
                    select(Obras)
                    .join(ObrasAsignaciones)
                    .where(
                        ObrasAsignaciones.id_usuario == current_user.id_usuario,
                        col(ObrasAsignaciones.fecha_inicio_asignacion) <= hoy,
                        or_(
                            col(ObrasAsignaciones.fecha_fin_asignacion).is_(None),
                            col(ObrasAsignaciones.fecha_fin_asignacion) >= hoy,
                        ),
                    )
                    .offset(skip)
                    .limit(limit)
                ).all()
            )
        return [ObraContratoService._enriquecer_obra_public(session, o) for o in obras]

    @staticmethod
    def obtener_obra(session: Session, id_obra: int) -> Obras:
        obra = session.get(Obras, id_obra)
        if not obra:
            raise HTTPException(status_code=404, detail="Obra no encontrada.")
        return obra

    @staticmethod
    def actualizar_obra(
        session: Session, id_obra: int, obra_in: models.ObraUpdate, admin: Usuarios, ip_origen: str
    ) -> models.ObraPublic:
        obra = ObraContratoService.obtener_obra(session, id_obra)

        # RN-ADM-04.5: Congelamiento de línea base tras firma de Nota de Apertura o Estimaciones
        if ObraContratoService.linea_base_congelada(session, id_obra):
            if any([
                obra_in.presupuesto_total is not None,
                obra_in.fecha_inicio is not None,
                obra_in.fecha_fin is not None,
            ]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "RN-ADM-04.5: Línea base contractual congelada. La obra ya cuenta con Nota de Apertura "
                        "firmada o estimaciones registradas; no se pueden editar montos ni plazos directamente."
                    )
                )

        datos = obra_in.model_dump(exclude_unset=True)
        for campo, valor in datos.items():
            setattr(obra, campo, valor)

        if obra.fecha_fin < obra.fecha_inicio:
            raise HTTPException(status_code=400, detail="La fecha de término no puede ser menor a la de inicio.")

        session.add(obra)
        session.commit()
        session.refresh(obra)

        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=admin.id_usuario,
            id_obra=obra.id_obra,
            tipo_accion="MODIFICACION",
            accion_ejecutada="EDICION_OBRA",
            descripcion=f"Actualización de datos de la obra ID {id_obra}",
            ip_origen=ip_origen
        )
        return ObraContratoService._enriquecer_obra_public(session, obra)

    @staticmethod
    def registrar_contrato(
        session: Session, contrato_in: models.ContratoCreate, admin: Usuarios, ip_origen: str
    ) -> Contratos:
        obra = ObraContratoService.obtener_obra(session, contrato_in.id_obra)
        contratista = session.get(Contratistas, contrato_in.id_contratista)
        if not contratista or not contratista.activo:
            raise HTTPException(status_code=404, detail="Empresa contratista no encontrada o inactiva.")

        if contrato_in.monto_contrato > obra.presupuesto_total:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El monto del contrato no puede superar el presupuesto total autorizado de la obra."
            )

        if contrato_in.archivo_contrato:
            validar_formato_y_tamano_archivo(contrato_in.archivo_contrato, (".pdf",))

        existente_obra = session.exec(
            select(Contratos).where(Contratos.id_obra == contrato_in.id_obra)
        ).first()
        if existente_obra:
            raise HTTPException(status_code=400, detail="Esta obra ya tiene un contrato principal registrado.")

        existente_num = session.exec(
            select(Contratos).where(Contratos.numero_contrato == contrato_in.numero_contrato)
        ).first()
        if existente_num:
            raise HTTPException(status_code=400, detail="El número de contrato ya existe en el sistema.")

        est_vigente = session.exec(
            select(CatEstatus).where(CatEstatus.ambito == "CONTRATO", CatEstatus.clave == "VIGENTE")
        ).first()

        nuevo_contrato = Contratos(
            id_obra=contrato_in.id_obra,
            id_contratista=contrato_in.id_contratista,
            id_estatus=est_vigente.id_estatus if est_vigente else 1,
            numero_contrato=contrato_in.numero_contrato,
            monto_contrato=contrato_in.monto_contrato,
            archivo_contrato=contrato_in.archivo_contrato
        )
        session.add(nuevo_contrato)
        session.commit()
        session.refresh(nuevo_contrato)

        # RN-ADM-04.2: Evaluar si ya cumple condiciones para pasar a EN_EJECUCION
        AsignacionObraService.evaluar_activacion_obra(session, contrato_in.id_obra)

        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=admin.id_usuario,
            id_obra=contrato_in.id_obra,
            tipo_accion="CREACION",
            accion_ejecutada="REGISTRO_CONTRATO",
            descripcion=f"Alta de contrato {nuevo_contrato.numero_contrato}",
            ip_origen=ip_origen
        )
        return nuevo_contrato

    @staticmethod
    def actualizar_contrato(
        session: Session, id_contrato: int, contrato_in: models.ContratoUpdate, admin: Usuarios
    ) -> Contratos:
        contrato = session.get(Contratos, id_contrato)
        if not contrato:
            raise HTTPException(status_code=404, detail="Contrato no encontrado.")

        if ObraContratoService.linea_base_congelada(session, contrato.id_obra):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RN-ADM-04.5: No se puede modificar directamente el contrato una vez abierta la bitácora."
            )

        if contrato_in.archivo_contrato:
            validar_formato_y_tamano_archivo(contrato_in.archivo_contrato, (".pdf",))

        obra = ObraContratoService.obtener_obra(session, contrato.id_obra)
        if contrato_in.monto_contrato and contrato_in.monto_contrato > obra.presupuesto_total:
            raise HTTPException(
                status_code=400,
                detail="El monto del contrato no puede exceder el presupuesto total de la obra."
            )

        datos = contrato_in.model_dump(exclude_unset=True)
        for campo, valor in datos.items():
            setattr(contrato, campo, valor)

        session.add(contrato)
        session.commit()
        session.refresh(contrato)
        return contrato

    @staticmethod
    def registrar_poliza(
        session: Session, poliza_in: models.PolizaCreate, admin: Usuarios, ip_origen: str
    ) -> Polizas:
        contrato = session.get(Contratos, poliza_in.id_contrato)
        if not contrato:
            raise HTTPException(status_code=404, detail="Contrato no encontrado.")

        tipo_poliza = session.get(CatTipoPoliza, poliza_in.id_tipo_poliza)
        if not tipo_poliza or not tipo_poliza.activo:
            raise HTTPException(status_code=404, detail="Tipo de póliza no válido o inactivo.")

        validar_formato_y_tamano_archivo(poliza_in.archivo_poliza, (".pdf",))

        duplicada = session.exec(
            select(Polizas).where(Polizas.numero_poliza == poliza_in.numero_poliza)
        ).first()
        if duplicada:
            raise HTTPException(status_code=400, detail="El número de póliza ya se encuentra registrado.")

        nueva_poliza = Polizas(
            id_contrato=poliza_in.id_contrato,
            id_tipo_poliza=poliza_in.id_tipo_poliza,
            numero_poliza=poliza_in.numero_poliza,
            fecha_vencimiento=poliza_in.fecha_vencimiento,
            archivo_poliza=poliza_in.archivo_poliza
        )
        session.add(nueva_poliza)
        session.commit()
        session.refresh(nueva_poliza)

        # RN-ADM-04.2: Evaluar activación automática de la obra a EN_EJECUCION
        AsignacionObraService.evaluar_activacion_obra(session, contrato.id_obra)

        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=admin.id_usuario,
            id_obra=contrato.id_obra,
            tipo_accion="CREACION",
            accion_ejecutada="REGISTRO_POLIZA",
            descripcion=f"Registro de póliza {nueva_poliza.numero_poliza}",
            ip_origen=ip_origen
        )
        return nueva_poliza

    @staticmethod
    def actualizar_poliza_renovada(
        session: Session, id_poliza: int, poliza_in: models.PolizaUpdate, admin: Usuarios
    ) -> Polizas:
        """RN-ADM-04.5: Permite al Administrador actualizar archivos de pólizas renovadas incluso en ejecución."""
        poliza = session.get(Polizas, id_poliza)
        if not poliza:
            raise HTTPException(status_code=404, detail="Póliza no encontrada.")

        if poliza_in.archivo_poliza:
            validar_formato_y_tamano_archivo(poliza_in.archivo_poliza, (".pdf",))
            poliza.archivo_poliza = poliza_in.archivo_poliza
        if poliza_in.fecha_vencimiento:
            poliza.fecha_vencimiento = poliza_in.fecha_vencimiento

        session.add(poliza)
        session.commit()
        session.refresh(poliza)
        return poliza


# ==========================================
# 3. SERVICIO: CATÁLOGO DE CONCEPTOS, APU Y PROGRAMA (RF-SUPT-01, RF-SUPT-02, RF-RES-04, RF-SUP-04)
# ==========================================
class CatalogoProgramaService:
    @staticmethod
    def cargar_conceptos_ordinarios(
        session: Session, conceptos_in: List[models.ConceptoCatalogoCreate]
    ) -> List[ConceptosCatalogo]:
        if not conceptos_in:
            raise HTTPException(status_code=400, detail="Debe enviar al menos un concepto para cargar.")

        id_obra = conceptos_in[0].id_obra
        obra = ObraContratoService.obtener_obra(session, id_obra)

        # RN-SUPT-01.3: Congelamiento de línea base
        if ObraContratoService.linea_base_congelada(session, id_obra):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "RN-SUPT-01.3: Línea base congelada. No se pueden agregar conceptos ordinarios "
                    "una vez firmada la apertura o iniciadas las estimaciones."
                )
            )

        contrato = session.exec(select(Contratos).where(Contratos.id_obra == id_obra)).first()
        tope_financiero = min(obra.presupuesto_total, contrato.monto_contrato) if contrato else obra.presupuesto_total

        existentes = list(
            session.exec(
                select(ConceptosCatalogo).where(ConceptosCatalogo.id_obra == id_obra)
            ).all()
        )
        importe_actual = sum(
            (c.cantidad_presupuestada * c.precio_unitario for c in existentes),
            Decimal("0.00")
        )
        claves_existentes = {c.clave_concepto.upper() for c in existentes}

        importe_nuevo = Decimal("0.00")
        claves_lote = set()
        for item in conceptos_in:
            if item.id_obra != id_obra:
                raise HTTPException(status_code=400, detail="Todos los conceptos del lote deben pertenecer a la misma obra.")
            clave_norm = item.clave_concepto.strip().upper()
            # RN-SUPT-01.2: Unicidad de clave por obra
            if clave_norm in claves_existentes or clave_norm in claves_lote:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"RN-SUPT-01.2: La clave de concepto '{clave_norm}' ya existe en esta obra."
                )
            claves_lote.add(clave_norm)
            unidad = session.get(CatUnidadesMedida, item.id_unidad)
            if not unidad or not unidad.activo:
                raise HTTPException(status_code=404, detail=f"Unidad de medida ID {item.id_unidad} no válida.")
            importe_nuevo += (item.cantidad_presupuestada * item.precio_unitario)

        # RN-SUPT-01.1: Tope presupuestal estricto
        if (importe_actual + importe_nuevo) > tope_financiero:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"RN-SUPT-01.1: La sumatoria del catálogo (${importe_actual + importe_nuevo:,.2f}) "
                    f"excede el tope contractual/presupuestal (${tope_financiero:,.2f})."
                )
            )

        tipo_ord = session.exec(
            select(CatTipoConcepto).where(CatTipoConcepto.clave == "ORDINARIO")
        ).first()

        creados: List[ConceptosCatalogo] = []
        for item in conceptos_in:
            nuevo = ConceptosCatalogo(
                id_obra=id_obra,
                id_tipo_concepto=tipo_ord.id_tipo_concepto if tipo_ord else 1,
                id_unidad=item.id_unidad,
                clave_concepto=item.clave_concepto.strip().upper(),
                descripcion=item.descripcion,
                cantidad_presupuestada=item.cantidad_presupuestada,
                cantidad_adicional_autorizada=Decimal("0.00"),
                precio_unitario=item.precio_unitario,
                dictamen_apu_url=None,
                autorizado_por_residente=True
            )
            session.add(nuevo)
            creados.append(nuevo)

        session.commit()
        for c in creados:
            session.refresh(c)
        return creados

    @staticmethod
    def editar_concepto_ordinario(
        session: Session, id_concepto: int, concepto_in: models.ConceptoCatalogoUpdate
    ) -> ConceptosCatalogo:
        concepto = session.get(ConceptosCatalogo, id_concepto)
        if not concepto:
            raise HTTPException(status_code=404, detail="Concepto no encontrado.")

        if ObraContratoService.linea_base_congelada(session, concepto.id_obra):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RN-SUPT-01.3: Los precios unitarios y volúmenes originales están bloqueados e inmutables."
            )

        datos = concepto_in.model_dump(exclude_unset=True)
        for campo, valor in datos.items():
            setattr(concepto, campo, valor)

        obra = ObraContratoService.obtener_obra(session, concepto.id_obra)
        contrato = session.exec(select(Contratos).where(Contratos.id_obra == concepto.id_obra)).first()
        tope = min(obra.presupuesto_total, contrato.monto_contrato) if contrato else obra.presupuesto_total

        todos = list(
            session.exec(
                select(ConceptosCatalogo).where(ConceptosCatalogo.id_obra == concepto.id_obra)
            ).all()
        )
        suma_total = sum(
            (
                (concepto.cantidad_presupuestada * concepto.precio_unitario)
                if c.id_concepto == id_concepto
                else (c.cantidad_presupuestada * c.precio_unitario)
                for c in todos
            ),
            Decimal("0.00")
        )
        if suma_total > tope:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"RN-SUPT-01.1: La modificación rebasa el tope presupuestal (${tope:,.2f})."
            )

        session.add(concepto)
        session.commit()
        session.refresh(concepto)
        return concepto

    @staticmethod
    def inyectar_concepto_extraordinario(
        session: Session,
        inyeccion_in: models.ConceptoExtraordinarioInyeccion,
        residente: Usuarios,
        ip_origen: str
    ) -> ConceptosCatalogo:
        """
        RF-RES-04 (RN-RES-04.1 y RN-RES-04.2): Autorización e inyección de precios extraordinarios
        con validación obligatoria de dictamen APU (.pdf) y firma electrónica del Residente.
        """
        obra = ObraContratoService.obtener_obra(session, inyeccion_in.id_obra)
        validar_formato_y_tamano_archivo(inyeccion_in.dictamen_apu_url, (".pdf",))

        validar_firma_electronica_y_generar_sello(
            firma_plana=inyeccion_in.firma_electronica_residente,
            firma_hash_usuario=residente.firma_electronica,
            id_usuario=residente.id_usuario,
            referencia=f"APU-EXTRAORDINARIO:{inyeccion_in.clave_concepto}"
        )

        clave_norm = inyeccion_in.clave_concepto.strip().upper()
        duplicado = session.exec(
            select(ConceptosCatalogo).where(
                ConceptosCatalogo.id_obra == obra.id_obra,
                ConceptosCatalogo.clave_concepto == clave_norm
            )
        ).first()
        if duplicado:
            raise HTTPException(
                status_code=400,
                detail=f"RN-SUPT-01.2: La clave '{clave_norm}' ya existe en el catálogo de esta obra."
            )

        tipo_ext = session.exec(
            select(CatTipoConcepto).where(CatTipoConcepto.clave == "EXTRAORDINARIO")
        ).first()

        nuevo_ext = ConceptosCatalogo(
            id_obra=obra.id_obra,
            id_tipo_concepto=tipo_ext.id_tipo_concepto if tipo_ext else 2,
            id_unidad=inyeccion_in.id_unidad,
            clave_concepto=clave_norm,
            descripcion=inyeccion_in.descripcion,
            cantidad_presupuestada=inyeccion_in.cantidad_presupuestada,
            cantidad_adicional_autorizada=Decimal("0.00"),
            precio_unitario=inyeccion_in.precio_unitario,
            dictamen_apu_url=inyeccion_in.dictamen_apu_url,
            autorizado_por_residente=True
        )
        session.add(nuevo_ext)
        session.commit()
        session.refresh(nuevo_ext)

        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=residente.id_usuario,
            id_obra=obra.id_obra,
            tipo_accion="AUTORIZACION",
            accion_ejecutada="INYECCION_CONCEPTO_EXTRAORDINARIO_APU",
            descripcion=f"Concepto extraordinario {clave_norm} autorizado con APU",
            ip_origen=ip_origen
        )
        return nuevo_ext

    @staticmethod
    def registrar_actividad_programa(
        session: Session, prog_in: models.ProgramaEjecucionCreate
    ) -> ProgramaEjecucion:
        """
        RF-SUPT-02 (RN-SUPT-02.1 a RN-SUPT-02.3): Alineación al plazo contractual,
        consistencia de volúmenes y bloqueo tras inicio de ejecución.
        """
        concepto = session.get(ConceptosCatalogo, prog_in.id_concepto)
        if not concepto:
            raise HTTPException(status_code=404, detail="El concepto especificado no existe.")

        obra = ObraContratoService.obtener_obra(session, concepto.id_obra)

        # RN-SUPT-02.3: Bloqueo de edición manual tras inicio del contrato
        if ObraContratoService.linea_base_congelada(session, obra.id_obra):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "RN-SUPT-02.3: El programa de ejecución se encuentra bloqueado. "
                    "Los desplazamientos de fechas solo ocurren automáticamente por suspensión/reanudación."
                )
            )

        if prog_in.fecha_fin_prog < prog_in.fecha_inicio_prog:
            raise HTTPException(status_code=400, detail="La fecha fin programada no puede ser menor a la de inicio.")

        # RN-SUPT-02.1: Alineación al plazo contractual de la obra
        if prog_in.fecha_inicio_prog < obra.fecha_inicio or prog_in.fecha_fin_prog > obra.fecha_fin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"RN-SUPT-02.1: Las fechas de la actividad ({prog_in.fecha_inicio_prog} a {prog_in.fecha_fin_prog}) "
                    f"deben estar dentro del plazo contractual ({obra.fecha_inicio} a {obra.fecha_fin})."
                )
            )

        # RN-SUPT-02.2: La suma programada no puede exceder la cantidad presupuestada del concepto
        actividades_previas = list(
            session.exec(
                select(ProgramaEjecucion).where(ProgramaEjecucion.id_concepto == concepto.id_concepto)
            ).all()
        )
        suma_previa = sum((a.cant_programada for a in actividades_previas), Decimal("0.00"))
        if (suma_previa + prog_in.cant_programada) > concepto.cantidad_presupuestada:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"RN-SUPT-02.2: La cantidad programada acumulada ({suma_previa + prog_in.cant_programada}) "
                    f"supera la cantidad presupuestada del concepto ({concepto.cantidad_presupuestada})."
                )
            )

        nueva_act = ProgramaEjecucion(
            id_concepto=prog_in.id_concepto,
            fecha_inicio_prog=prog_in.fecha_inicio_prog,
            fecha_fin_prog=prog_in.fecha_fin_prog,
            cant_programada=prog_in.cant_programada
        )
        session.add(nueva_act)
        session.commit()
        session.refresh(nueva_act)
        return nueva_act

    @staticmethod
    def consultar_gantt_obra(session: Session, id_obra: int) -> List[ProgramaEjecucion]:
        return list(
            session.exec(
                select(ProgramaEjecucion)
                .join(ConceptosCatalogo)
                .where(ConceptosCatalogo.id_obra == id_obra)
                .order_by(col(ProgramaEjecucion.fecha_inicio_prog).asc())
            ).all()
        )

    @staticmethod
    def monitorear_ruta_critica(
        session: Session, id_obra: int, fecha_corte: Optional[date] = None
    ) -> List[models.ActividadRutaCriticaPublic]:
        """
        RF-SUP-04 y RN-SUP-04.1: Compara cant_programada contra cant_aprobada en Generadores_Validacion,
        marcando en rojo toda actividad cuya fecha_fin_prog haya vencido sin alcanzar el 100%.
        """
        corte = fecha_corte or date.today()
        actividades = CatalogoProgramaService.consultar_gantt_obra(session, id_obra)
        resultado: List[models.ActividadRutaCriticaPublic] = []

        for act in actividades:
            concepto = session.get(ConceptosCatalogo, act.id_concepto)
            generadores = list(
                session.exec(
                    select(Generadores).where(Generadores.id_concepto == act.id_concepto)
                ).all()
            )

            aprobado_concepto = Decimal("0.00")
            for g in generadores:
                ult_val = session.exec(
                    select(GeneradoresValidacion)
                    .where(GeneradoresValidacion.id_generador == g.id_generador)
                    .order_by(col(GeneradoresValidacion.version_revisada).desc())
                ).first()
                if ult_val:
                    aprobado_concepto += ult_val.cant_aprobada

            pct = (
                _redondear_2((aprobado_concepto / act.cant_programada) * Decimal("100.00"))
                if act.cant_programada > 0
                else Decimal("0.00")
            )
            en_rojo = (corte > act.fecha_fin_prog) and (aprobado_concepto < act.cant_programada)
            estado = "EN_ROJO_ATRASO_CRITICO" if en_rojo else ("COMPLETADA" if pct >= Decimal("100.00") else "EN_TIEMPO")

            resultado.append(
                models.ActividadRutaCriticaPublic(
                    id_actividad=act.id_actividad,
                    id_concepto=act.id_concepto,
                    clave_concepto=concepto.clave_concepto if concepto else "",
                    descripcion_concepto=concepto.descripcion if concepto else "",
                    fecha_inicio_prog=act.fecha_inicio_prog,
                    fecha_fin_prog=act.fecha_fin_prog,
                    cant_programada=act.cant_programada,
                    cant_aprobada_acumulada=aprobado_concepto,
                    porcentaje_cumplimiento=min(Decimal("100.00"), pct),
                    en_rojo_atraso=en_rojo,
                    estado_actividad=estado
                )
            )
        return resultado


# ==========================================
# 4. SERVICIO: DASHBOARD DIRECTIVO, GANTT MACRO, REPORTES Y FINIQUITO (RF-DIR-01 a 04, RF-RES-05)
# ==========================================
class DirectivoFiniquitoService:
    @staticmethod
    def calcular_avances_obra(session: Session, obra: Obras, fecha_corte: Optional[date] = None) -> dict:
        """
        RN-DIR-01.2 a RN-DIR-01.6: Calcula Avance Físico Programado, Avance Financiero Programado,
        Avance Físico Real (respaldado por Generadores_Validacion) y Avance Financiero Real.
        """
        corte = fecha_corte or date.today()
        contrato = session.exec(select(Contratos).where(Contratos.id_obra == obra.id_obra)).first()
        monto_contrato = contrato.monto_contrato if contrato else obra.presupuesto_total

        # 1. Importe programado a la fecha de corte (RN-DIR-01.2 y RN-DIR-01.3)
        actividades = list(
            session.exec(
                select(ProgramaEjecucion)
                .join(ConceptosCatalogo)
                .where(
                    ConceptosCatalogo.id_obra == obra.id_obra,
                    col(ProgramaEjecucion.fecha_fin_prog) <= corte
                )
            ).all()
        )

        importe_programado = Decimal("0.00")
        for act in actividades:
            conc = session.get(ConceptosCatalogo, act.id_concepto)
            if conc:
                importe_programado += (act.cant_programada * conc.precio_unitario)

        pct_fisico_prog = (
            _redondear_2((importe_programado / obra.presupuesto_total) * Decimal("100.00"))
            if obra.presupuesto_total > 0 else Decimal("0.00")
        )
        pct_fin_prog = (
            _redondear_2((importe_programado / monto_contrato) * Decimal("100.00"))
            if monto_contrato > 0 else Decimal("0.00")
        )

        # 2. Importe físico ejecutado real validado en Generadores_Validacion (RN-DIR-01.5)
        generadores_obra = list(
            session.exec(
                select(Generadores)
                .join(Estimaciones)
                .where(Estimaciones.id_obra == obra.id_obra)
            ).all()
        )

        importe_fisico_real = Decimal("0.00")
        for gen in generadores_obra:
            ult_val = session.exec(
                select(GeneradoresValidacion)
                .where(GeneradoresValidacion.id_generador == gen.id_generador)
                .order_by(col(GeneradoresValidacion.version_revisada).desc())
            ).first()
            if ult_val:
                conc = session.get(ConceptosCatalogo, gen.id_concepto)
                if conc:
                    importe_fisico_real += (ult_val.cant_aprobada * conc.precio_unitario)

        pct_fisico_real = (
            _redondear_2((importe_fisico_real / obra.presupuesto_total) * Decimal("100.00"))
            if obra.presupuesto_total > 0 else Decimal("0.00")
        )

        # 3. Avance financiero real (RN-DIR-01.4)
        pagos = list(
            session.exec(
                select(EstimacionesPagadas)
                .join(Estimaciones)
                .where(Estimaciones.id_obra == obra.id_obra)
            ).all()
        )
        suma_pagada = sum((p.monto_pagado for p in pagos), Decimal("0.00"))

        if suma_pagada == Decimal("0.00"):
            # Si aún no hay pagos liquidados, toma el monto autorizado neto de revisiones APROBADAS
            est_aprob = session.exec(
                select(CatEstatus).where(CatEstatus.ambito == "REVISION", CatEstatus.clave == "APROBADA")
            ).first()
            if est_aprob:
                revs = list(
                    session.exec(
                        select(RevisionEstimaciones)
                        .join(Estimaciones)
                        .where(
                            Estimaciones.id_obra == obra.id_obra,
                            RevisionEstimaciones.id_estatus_revision == est_aprob.id_estatus
                        )
                    ).all()
                )
                suma_pagada = sum((r.monto_autorizado_neto for r in revs), Decimal("0.00"))

        pct_fin_real = (
            _redondear_2((suma_pagada / obra.presupuesto_total) * Decimal("100.00"))
            if obra.presupuesto_total > 0 else Decimal("0.00")
        )

        # 4. Alertas normativas de 15 días en revisiones pendientes (RF-SUP-06)
        est_pend = session.exec(
            select(CatEstatus).where(CatEstatus.ambito == "REVISION", CatEstatus.clave == "PENDIENTE")
        ).first()
        alertas: List[str] = []
        if est_pend:
            revs_pendientes = list(
                session.exec(
                    select(RevisionEstimaciones)
                    .join(Estimaciones)
                    .where(
                        Estimaciones.id_obra == obra.id_obra,
                        RevisionEstimaciones.id_estatus_revision == est_pend.id_estatus,
                        col(RevisionEstimaciones.fecha_autorizacion).is_(None)
                    )
                ).all()
            )
            for rp in revs_pendientes:
                dias = (corte - rp.fecha_recepcion).days
                if dias >= 15:
                    alertas.append(
                        f"ALERTA CRÍTICA ROJA (RF-SUP-06): Revisión ID {rp.id_revision} lleva {dias} días naturales sin dictamen (Plazo legal: 15 días)."
                    )
                elif dias >= 10:
                    alertas.append(
                        f"ALERTA PREVENTIVA AMARILLA (RF-SUP-06): Revisión ID {rp.id_revision} lleva {dias} días naturales ({15 - dias} días restantes)."
                    )

        return {
            "monto_contrato": monto_contrato,
            "pct_fisico_prog": min(Decimal("100.00"), pct_fisico_prog),
            "pct_fisico_real": min(Decimal("100.00"), pct_fisico_real),
            "pct_fin_prog": min(Decimal("100.00"), pct_fin_prog),
            "pct_fin_real": min(Decimal("100.00"), pct_fin_real),
            "alertas": alertas,
        }

    @staticmethod
    def registrar_corte_avance(session: Session, id_obra: int, fecha_corte: Optional[date] = None) -> AvancesFisicos:
        obra = ObraContratoService.obtener_obra(session, id_obra)
        corte = fecha_corte or date.today()
        metricas = DirectivoFiniquitoService.calcular_avances_obra(session, obra, corte)

        if metricas["pct_fin_real"] > metricas["pct_fisico_real"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RN-DIR-01.6: Violación de control presupuestal: El avance financiero no puede superar al avance físico real ejecutado."
            )

        nuevo_corte = AvancesFisicos(
            id_obra=obra.id_obra,
            fecha_corte=corte,
            porcentaje_fisico=metricas["pct_fisico_real"],
            porcentaje_fisico_programado=metricas["pct_fisico_prog"],
            porcentaje_financiero_real=metricas["pct_fin_real"],
            porcentaje_financiero_programado=metricas["pct_fin_prog"]
        )
        session.add(nuevo_corte)
        session.commit()
        session.refresh(nuevo_corte)
        return nuevo_corte

    @staticmethod
    def obtener_dashboard_ejecutivo(session: Session) -> List[models.DashboardObraItem]:
        """RF-DIR-01: Tablero de control de avance físico y financiero de todas las obras."""
        obras = list(session.exec(select(Obras)).all())
        tablero: List[models.DashboardObraItem] = []
        for obra in obras:
            est = session.get(CatEstatus, obra.id_estatus)
            m = DirectivoFiniquitoService.calcular_avances_obra(session, obra)
            tablero.append(
                models.DashboardObraItem(
                    id_obra=obra.id_obra,
                    nombre_obra=obra.nombre_obra,
                    estado_general=est.clave if est else "DESCONOCIDO",
                    presupuesto_total=obra.presupuesto_total,
                    monto_contrato=m["monto_contrato"],
                    avance_fisico_programado_pct=m["pct_fisico_prog"],
                    avance_fisico_real_pct=m["pct_fisico_real"],
                    avance_financiero_programado_pct=m["pct_fin_prog"],
                    avance_financiero_real_pct=m["pct_fin_real"],
                    cumple_candado_fisico_financiero=(m["pct_fin_real"] <= m["pct_fisico_real"]),
                    alertas_plazo_revision=m["alertas"]
                )
            )
        return tablero

    @staticmethod
    def obtener_calendario_gantt_macro(session: Session) -> List[models.GanttMacroItem]:
        """
        RF-DIR-02 y RN-DIR-02.1: Diagrama de Gantt macro con semáforo de estado:
        - VERDE (EN_TIEMPO): Avance físico real >= 95% del programado a la fecha actual.
        - AMARILLO_ROJO (CON_ATRASO): Inferior al 95% del programado o fecha actual > fecha_fin sin estar TERMINADA/CERRADA.
        - GRIS_ALERTA (SUSPENDIDA): Cuando la obra está en estado SUSPENDIDA.
        """
        hoy = date.today()
        obras = list(session.exec(select(Obras)).all())
        items: List[models.GanttMacroItem] = []

        for obra in obras:
            est = session.get(CatEstatus, obra.id_estatus)
            clave_est = est.clave if est else "EN_CONFIGURACION"
            contrato = session.exec(select(Contratos).where(Contratos.id_obra == obra.id_obra)).first()
            m = DirectivoFiniquitoService.calcular_avances_obra(session, obra, hoy)

            prog = m["pct_fisico_prog"]
            real = m["pct_fisico_real"]

            if clave_est == "SUSPENDIDA":
                semaforo = "GRIS_ALERTA (SUSPENDIDA)"
            elif hoy > obra.fecha_fin and clave_est not in {"FINIQUITADA", "CERRADA"}:
                semaforo = "AMARILLO_ROJO (CON_ATRASO)"
            elif prog > Decimal("0.00") and real < _redondear_2(prog * Decimal("0.95")):
                semaforo = "AMARILLO_ROJO (CON_ATRASO)"
            else:
                semaforo = "VERDE (EN_TIEMPO)"

            items.append(
                models.GanttMacroItem(
                    id_obra=obra.id_obra,
                    nombre_obra=obra.nombre_obra,
                    numero_contrato=contrato.numero_contrato if contrato else None,
                    fecha_inicio=obra.fecha_inicio,
                    fecha_fin=obra.fecha_fin,
                    estado_general=clave_est,
                    avance_programado_pct=prog,
                    avance_real_pct=real,
                    semaforo=semaforo
                )
            )
        return items

    @staticmethod
    def exportar_reporte_financiero(
        session: Session, id_obra: int, usuario: Usuarios, ip_origen: str
    ) -> models.ReporteGerencialFinanciero:
        """
        RF-DIR-04 (RN-DIR-04.1 y RN-DIR-04.2): Consolida datos financieros y registra
        obligatoriamente la descarga en Auditoría Logs con fecha, hora e IP del Directivo.
        """
        obra = ObraContratoService.obtener_obra(session, id_obra)
        contrato = session.exec(select(Contratos).where(Contratos.id_obra == id_obra)).first()
        contratista = (
            session.get(Contratistas, contrato.id_contratista)
            if contrato else None
        )

        estimaciones = list(session.exec(select(Estimaciones).where(Estimaciones.id_obra == id_obra)).all())
        monto_bruto = sum((e.monto_bruto for e in estimaciones), Decimal("0.00"))
        amortizacion = sum((e.monto_amortizacion for e in estimaciones), Decimal("0.00"))

        est_aprob = session.exec(
            select(CatEstatus).where(CatEstatus.ambito == "REVISION", CatEstatus.clave == "APROBADA")
        ).first()
        monto_neto_aut = Decimal("0.00")
        if est_aprob:
            revs = list(
                session.exec(
                    select(RevisionEstimaciones)
                    .join(Estimaciones)
                    .where(
                        Estimaciones.id_obra == id_obra,
                        RevisionEstimaciones.id_estatus_revision == est_aprob.id_estatus
                    )
                ).all()
            )
            monto_neto_aut = sum((r.monto_autorizado_neto for r in revs), Decimal("0.00"))

        pagos = list(
            session.exec(
                select(EstimacionesPagadas)
                .join(Estimaciones)
                .where(Estimaciones.id_obra == id_obra)
            ).all()
        )
        monto_liquidado = sum((p.monto_pagado for p in pagos), Decimal("0.00"))

        presupuesto_base = contrato.monto_contrato if contrato else obra.presupuesto_total
        saldo_pendiente = max(Decimal("0.00"), presupuesto_base - monto_liquidado)

        # RN-DIR-04.2: Trazabilidad de descarga en Auditoría Logs
        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=usuario.id_usuario,
            id_obra=obra.id_obra,
            tipo_accion="CONSULTA_REPORTE",
            accion_ejecutada=f"EXPORTACION_REPORTE_GERENCIAL_OBRA_{obra.id_obra}_{int(date.today().strftime('%Y%m%d'))}",
            descripcion=f"Exportación de reporte gerencial financiero de obra ID {obra.id_obra}",
            ip_origen=ip_origen
        )

        return models.ReporteGerencialFinanciero(
            id_obra=obra.id_obra,
            nombre_obra=obra.nombre_obra,
            numero_contrato=contrato.numero_contrato if contrato else None,
            contratista=contratista.razon_social if contratista else None,
            presupuesto_total_contratado=presupuesto_base,
            monto_bruto_estimado=monto_bruto,
            amortizacion_anticipo_descontada=amortizacion,
            monto_neto_autorizado=monto_neto_aut,
            monto_efectivamente_liquidado=monto_liquidado,
            saldo_pendiente_por_ejercer=saldo_pendiente,
            fecha_generacion=date.today()
        )

    @staticmethod
    def generar_recepcion_y_finiquito(
        session: Session,
        id_obra: int,
        solicitud: models.FiniquitoSolicitud,
        residente: Usuarios,
        ip_origen: str
    ) -> models.ActaFiniquitoResumen:
        """
        RF-RES-05 (RN-RES-05.1 y RN-RES-05.2): Genera Acta de Recepción Física y Finiquito,
        verificando precondiciones estrictas (Aviso de Terminación con >= 6 fotos y 100% de
        estimaciones liquidadas) y pasando Obra y Contrato a FINIQUITADA / CERRADA.
        """
        obra = ObraContratoService.obtener_obra(session, id_obra)
        contrato = session.exec(select(Contratos).where(Contratos.id_obra == id_obra)).first()
        if not contrato:
            raise HTTPException(status_code=400, detail="La obra no cuenta con un contrato registrado.")

        sello = validar_firma_electronica_y_generar_sello(
            firma_plana=solicitud.firma_electronica_residente,
            firma_hash_usuario=residente.firma_electronica,
            id_usuario=residente.id_usuario,
            referencia=f"FINIQUITO-OBRA:{id_obra}"
        )

        # Precondición 1: Nota de AVISO_TERMINACION firmada por Superintendente con mínimo 6 fotos
        tipo_aviso = session.exec(
            select(CatTipoNotaBitacora).where(CatTipoNotaBitacora.clave == "AVISO_TERMINACION")
        ).first()
        nota_aviso = None
        if tipo_aviso:
            nota_aviso = session.exec(
                select(BitacoraNotas).where(
                    BitacoraNotas.id_obra == id_obra,
                    BitacoraNotas.id_tipo_nota == tipo_aviso.id_tipo_nota,
                    col(BitacoraNotas.firmada).is_(True)
                )
            ).first()
        if not nota_aviso:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RF-RES-05: Precondición incumplida. No existe nota de AVISO_TERMINACION firmada en bitácora."
            )

        num_fotos = session.exec(
            select(func.count(col(EvidenciaAdjunta.id_evidencia))).where(
                EvidenciaAdjunta.id_nota == nota_aviso.id_nota
            )
        ).one()
        if num_fotos < 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"RF-RES-05 / RN-SUPT-05.2: El Aviso de Terminación requiere mínimo 6 fotografías (actuales: {num_fotos})."
            )

        # Precondición 2: Ninguna estimación pendiente; todas deben estar LIQUIDADAS en Estimaciones_Pagadas
        estimaciones = list(session.exec(select(Estimaciones).where(Estimaciones.id_obra == id_obra)).all())
        monto_ord = Decimal("0.00")
        monto_adic = Decimal("0.00")
        monto_ext = Decimal("0.00")
        total_amortizado = Decimal("0.00")
        saldo_liquidado = Decimal("0.00")

        for est in estimaciones:
            pago = session.get(EstimacionesPagadas, est.id_estimacion)
            if not pago:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"RF-RES-05: Precondición incumplida. La estimación #{est.numero_estimacion} "
                        "no se encuentra LIQUIDADA en Estimaciones_Pagadas."
                    )
                )
            tipo_est = session.get(CatTipoEstimacion, est.id_tipo_estimacion)
            clave_t = tipo_est.clave if tipo_est else "ORDINARIA"
            if clave_t == "ORDINARIA":
                monto_ord += est.monto_bruto
            elif clave_t == "CANTIDADES_ADICIONALES":
                monto_adic += est.monto_bruto
            elif clave_t == "EXTRAORDINARIA":
                monto_ext += est.monto_bruto

            total_amortizado += est.monto_amortizacion
            saldo_liquidado += pago.monto_pagado

        # RN-RES-05.2: Cambiar estado de Obra y Contrato a FINIQUITADA / FINIQUITADO
        est_obra_fin = session.exec(
            select(CatEstatus).where(CatEstatus.ambito == "OBRA", CatEstatus.clave == "FINIQUITADA")
        ).first()
        est_cont_fin = session.exec(
            select(CatEstatus).where(CatEstatus.ambito == "CONTRATO", CatEstatus.clave == "FINIQUITADO")
        ).first()
        if est_obra_fin:
            obra.id_estatus = est_obra_fin.id_estatus
            session.add(obra)
        if est_cont_fin:
            contrato.id_estatus = est_cont_fin.id_estatus
            session.add(contrato)

        session.commit()

        AuditoriaService.registrar_evento(
            session=session,
            id_usuario=residente.id_usuario,
            id_obra=obra.id_obra,
            tipo_accion="AUTORIZACION",
            accion_ejecutada=f"EMISION_FINIQUITO_OBRA_{obra.id_obra}",
            descripcion=f"Recepción física y finiquito de contrato {contrato.numero_contrato}",
            ip_origen=ip_origen
        )

        return models.ActaFiniquitoResumen(
            id_obra=obra.id_obra,
            nombre_obra=obra.nombre_obra,
            numero_contrato=contrato.numero_contrato,
            estado_obra="FINIQUITADA",
            estado_contrato="FINIQUITADO",
            monto_original_contratado=contrato.monto_contrato,
            monto_ejercido_ordinario=monto_ord,
            monto_ejercido_adicionales=monto_adic,
            monto_ejercido_extraordinarios=monto_ext,
            monto_total_ejercido=(monto_ord + monto_adic + monto_ext),
            total_anticipo_amortizado=total_amortizado,
            saldo_final_liquidado=saldo_liquidado,
            sello_digital_residente=sello
        )
