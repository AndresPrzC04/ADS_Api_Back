from typing import List
from fastapi import HTTPException, status
from sqlmodel import Session, select
from . import models


# ==========================================
# 1. SERVICIO: EMPRESA CONTRATISTA
# ==========================================
class EmpresaContratistaService:
    @staticmethod
    def crear(session: Session, empresa_in: models.EmpresaContratistaCreate) -> models.EmpresaContratista:
        rfc_upper = empresa_in.rfc.upper()
        existente = session.exec(
            select(models.EmpresaContratista).where(models.EmpresaContratista.rfc == rfc_upper)
        ).first()
        if existente:
            raise HTTPException(status_code=400, detail="Ya existe una empresa contratista con este RFC.")

        nueva_empresa = models.EmpresaContratista.model_validate(empresa_in)
        nueva_empresa.rfc = rfc_upper
        session.add(nueva_empresa)
        session.commit()
        session.refresh(nueva_empresa)
        return nueva_empresa

    @staticmethod
    def consultar(session: Session, skip: int = 0, limit: int = 100) -> List[models.EmpresaContratista]:
        return session.exec(
            select(models.EmpresaContratista).offset(skip).limit(limit)
        ).all()

    @staticmethod
    def desactivar(session: Session, id_empresa: int) -> models.EmpresaContratista:
        empresa = session.get(models.EmpresaContratista, id_empresa)
        if not empresa:
            raise HTTPException(status_code=404, detail="Empresa contratista no encontrada.")
        empresa.estado = False
        session.add(empresa)
        session.commit()
        session.refresh(empresa)
        return empresa


# ==========================================
# 2. SERVICIO: OBRA Y AVANCE FÍSICO
# ==========================================
class ObraService:
    @staticmethod
    def crear(session: Session, obra_in: models.ObraCreate) -> models.Obra:
        if obra_in.fecha_fin < obra_in.fecha_inicio:
            raise HTTPException(status_code=400, detail="La fecha de fin no puede ser menor a la de inicio.")

        existente = session.exec(
            select(models.Obra).where(models.Obra.num_contrato == obra_in.num_contrato)
        ).first()
        if existente:
            raise HTTPException(status_code=400, detail="El número de contrato de obra ya existe.")

        nueva_obra = models.Obra.model_validate(obra_in)
        session.add(nueva_obra)
        session.commit()
        session.refresh(nueva_obra)
        return nueva_obra

    @staticmethod
    def consultar(session: Session, skip: int = 0, limit: int = 100) -> List[models.Obra]:
        return session.exec(select(models.Obra).offset(skip).limit(limit)).all()

    @staticmethod
    def obtener_por_id(session: Session, id_obra: int) -> models.Obra:
        obra = session.get(models.Obra, id_obra)
        if not obra:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obra no encontrada.")
        return obra

    @staticmethod
    def actualizar(session: Session, id_obra: int, obra_in: models.ObraUpdate) -> models.Obra:
        obra = ObraService.obtener_por_id(session, id_obra)
        if obra.estado == "CERRADA":
            raise HTTPException(status_code=400, detail="No se puede modificar una obra en estado CERRADA.")

        datos = obra_in.model_dump(exclude_unset=True)
        for campo, valor in datos.items():
            setattr(obra, campo, valor)

        session.add(obra)
        session.commit()
        session.refresh(obra)
        return obra

    @staticmethod
    def cerrar(session: Session, id_obra: int) -> models.Obra:
        obra = ObraService.obtener_por_id(session, id_obra)
        obra.estado = "CERRADA"
        session.add(obra)
        session.commit()
        session.refresh(obra)
        return obra

    @staticmethod
    def registrar_avance_fisico(session: Session, avance_in: models.AvanceFisicoCreate) -> models.AvanceFisico:
        ObraService.obtener_por_id(session, avance_in.id_obra)
        nuevo_avance = models.AvanceFisico.model_validate(avance_in)
        session.add(nuevo_avance)
        session.commit()
        session.refresh(nuevo_avance)
        return nuevo_avance


# ==========================================
# 3. SERVICIO: CONTRATOS Y PÓLIZAS
# ==========================================
class ContratoService:
    @staticmethod
    def registrar(session: Session, contrato_in: models.ContratoCreate) -> models.Contrato:
        ObraService.obtener_por_id(session, contrato_in.id_obra)
        empresa = session.get(models.EmpresaContratista, contrato_in.id_empresa_contratista)
        if not empresa:
            raise HTTPException(status_code=404, detail="Empresa contratista no encontrada.")

        nuevo_contrato = models.Contrato.model_validate(contrato_in)
        session.add(nuevo_contrato)
        session.commit()
        session.refresh(nuevo_contrato)
        return nuevo_contrato

    @staticmethod
    def consultar_por_obra(session: Session, id_obra: int) -> List[models.Contrato]:
        return session.exec(
            select(models.Contrato).where(models.Contrato.id_obra == id_obra)
        ).all()

    @staticmethod
    def actualizar_borrador(
        session: Session, id_contrato: int, contrato_in: models.ContratoUpdate
    ) -> models.Contrato:
        contrato = session.get(models.Contrato, id_contrato)
        if not contrato:
            raise HTTPException(status_code=404, detail="Contrato no encontrado.")
        if contrato.estado != "BORRADOR":
            raise HTTPException(status_code=400, detail="Solo se pueden editar contratos en estado BORRADOR.")

        datos = contrato_in.model_dump(exclude_unset=True)
        for campo, valor in datos.items():
            setattr(contrato, campo, valor)

        session.add(contrato)
        session.commit()
        session.refresh(contrato)
        return contrato

    @staticmethod
    def registrar_poliza(session: Session, poliza_in: models.PolizaCreate) -> models.Poliza:
        contrato = session.get(models.Contrato, poliza_in.id_contrato)
        if not contrato:
            raise HTTPException(status_code=404, detail="Contrato no encontrado para asociar la póliza.")

        nueva_poliza = models.Poliza.model_validate(poliza_in)
        session.add(nueva_poliza)
        session.commit()
        session.refresh(nueva_poliza)
        return nueva_poliza


# ==========================================
# 4. SERVICIO: CATÁLOGO DE CONCEPTOS E INSUMOS
# ==========================================
class CatalogoInsumoService:
    @staticmethod
    def crear_insumo(session: Session, insumo_in: models.InsumoCreate) -> models.Insumo:
        ObraService.obtener_por_id(session, insumo_in.id_obra)
        nuevo_insumo = models.Insumo.model_validate(insumo_in)
        session.add(nuevo_insumo)
        session.commit()
        session.refresh(nuevo_insumo)
        return nuevo_insumo

    @staticmethod
    def consultar_insumos_obra(session: Session, id_obra: int) -> List[models.Insumo]:
        return session.exec(
            select(models.Insumo).where(models.Insumo.id_obra == id_obra)
        ).all()

    @staticmethod
    def importar_linea_base(
        session: Session, conceptos_in: List[models.ConceptoCatalogoCreate]
    ) -> List[models.ConceptoCatalogo]:
        conceptos_creados = []
        for item in conceptos_in:
            nuevo_concepto = models.ConceptoCatalogo.model_validate(item)
            session.add(nuevo_concepto)
            conceptos_creados.append(nuevo_concepto)

        session.commit()
        for c in conceptos_creados:
            session.refresh(c)
        return conceptos_creados

    @staticmethod
    def consultar_conceptos_obra(session: Session, id_obra: int) -> List[models.ConceptoCatalogo]:
        return session.exec(
            select(models.ConceptoCatalogo).where(models.ConceptoCatalogo.id_obra == id_obra)
        ).all()

    @staticmethod
    def editar_antes_del_bloqueo(
        session: Session, id_concepto: int, concepto_in: models.ConceptoCatalogoUpdate
    ) -> models.ConceptoCatalogo:
        concepto = session.get(models.ConceptoCatalogo, id_concepto)
        if not concepto:
            raise HTTPException(status_code=404, detail="Concepto no encontrado.")
        if concepto.precio_bloqueado:
            raise HTTPException(status_code=400, detail="El precio de este concepto se encuentra bloqueado.")

        datos = concepto_in.model_dump(exclude_unset=True)
        for campo, valor in datos.items():
            setattr(concepto, campo, valor)

        session.add(concepto)
        session.commit()
        session.refresh(concepto)
        return concepto

    @staticmethod
    def bloquear_precio(session: Session, id_concepto: int) -> models.ConceptoCatalogo:
        concepto = session.get(models.ConceptoCatalogo, id_concepto)
        if not concepto:
            raise HTTPException(status_code=404, detail="Concepto no encontrado.")
        concepto.precio_bloqueado = True
        session.add(concepto)
        session.commit()
        session.refresh(concepto)
        return concepto

    @staticmethod
    def crear_concepto_elemento(
        session: Session, elemento_in: models.ConceptoElementoCreate
    ) -> models.ConceptoElemento:
        concepto = session.get(models.ConceptoCatalogo, elemento_in.id_concepto)
        if not concepto:
            raise HTTPException(status_code=404, detail="Concepto no encontrado.")
        if concepto.precio_bloqueado:
            raise HTTPException(status_code=400, detail="No se pueden asociar insumos a un concepto bloqueado.")

        insumo = session.get(models.Insumo, elemento_in.id_insumo)
        if not insumo:
            raise HTTPException(status_code=404, detail="Insumo no encontrado.")

        nuevo_elemento = models.ConceptoElemento.model_validate(elemento_in)
        session.add(nuevo_elemento)
        session.commit()
        session.refresh(nuevo_elemento)
        return nuevo_elemento

    @staticmethod
    def actualizar_borrador_elemento(
        session: Session, id_concepto_insumos: int, elemento_in: models.ConceptoElementoUpdate
    ) -> models.ConceptoElemento:
        elemento = session.get(models.ConceptoElemento, id_concepto_insumos)
        if not elemento:
            raise HTTPException(status_code=404, detail="Elemento no encontrado.")

        datos = elemento_in.model_dump(exclude_unset=True)
        for campo, valor in datos.items():
            setattr(elemento, campo, valor)

        session.add(elemento)
        session.commit()
        session.refresh(elemento)
        return elemento


# ==========================================
# 5. SERVICIO: PROGRAMA DE EJECUCIÓN (Gantt)
# ==========================================
class ProgramaEjecucionService:
    @staticmethod
    def crear(session: Session, prog_in: models.ProgramaEjecucionCreate) -> models.ProgramaEjecucion:
        if prog_in.fecha_fin_prog < prog_in.fecha_inicio_prog:
            raise HTTPException(status_code=400, detail="La fecha de fin no puede ser menor a la de inicio.")

        nueva_actividad = models.ProgramaEjecucion.model_validate(prog_in)
        session.add(nueva_actividad)
        session.commit()
        session.refresh(nueva_actividad)
        return nueva_actividad

    @staticmethod
    def consultar_gantt(session: Session, id_obra: int) -> List[models.ProgramaEjecucion]:
        return session.exec(
            select(models.ProgramaEjecucion)
            .where(models.ProgramaEjecucion.id_obra == id_obra)
            .order_by(models.ProgramaEjecucion.fecha_inicio_prog.asc())
        ).all()

    @staticmethod
    def recalendarizar(
        session: Session, id_actividad: int, prog_in: models.ProgramaEjecucionUpdate
    ) -> models.ProgramaEjecucion:
        actividad = session.get(models.ProgramaEjecucion, id_actividad)
        if not actividad:
            raise HTTPException(status_code=404, detail="Actividad no encontrada.")

        datos = prog_in.model_dump(exclude_unset=True)
        for campo, valor in datos.items():
            setattr(actividad, campo, valor)

        session.add(actividad)
        session.commit()
        session.refresh(actividad)
        return actividad