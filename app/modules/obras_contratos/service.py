from typing import List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from . import models, schemas


# ==========================================
# SERVICIO: EMPRESA CONTRATISTA
# ==========================================
class EmpresaContratistaService:
    @staticmethod
    def crear(db: Session, empresa_in: schemas.EmpresaContratistaCreate) -> models.EmpresaContratista:
        if db.query(models.EmpresaContratista).filter(models.EmpresaContratista.rfc == empresa_in.rfc.upper()).first():
            raise HTTPException(status_code=400, detail="Ya existe una empresa contratista con este RFC.")
        nueva_empresa = models.EmpresaContratista(**empresa_in.model_dump())
        nueva_empresa.rfc = nueva_empresa.rfc.upper()
        db.add(nueva_empresa)
        db.commit()
        db.refresh(nueva_empresa)
        return nueva_empresa

    @staticmethod
    def consultar(db: Session, skip: int = 0, limit: int = 100) -> List[models.EmpresaContratista]:
        return db.query(models.EmpresaContratista).offset(skip).limit(limit).all()

    @staticmethod
    def desactivar(db: Session, id_empresa: int) -> models.EmpresaContratista:
        empresa = db.query(models.EmpresaContratista).filter(
            models.EmpresaContratista.id_empresa_contratista == id_empresa
        ).first()
        if not empresa:
            raise HTTPException(status_code=404, detail="Empresa contratista no encontrada.")
        empresa.estado = False
        db.commit()
        db.refresh(empresa)
        return empresa


# ==========================================
# SERVICIO: OBRA Y AVANCE FÍSICO
# ==========================================
class ObraService:
    @staticmethod
    def crear(db: Session, obra_in: schemas.ObraCreate) -> models.Obra:
        if obra_in.fecha_fin < obra_in.fecha_inicio:
            raise HTTPException(status_code=400, detail="La fecha de fin no puede ser menor a la de inicio.")
        if db.query(models.Obra).filter(models.Obra.num_contrato == obra_in.num_contrato).first():
            raise HTTPException(status_code=400, detail="El número de contrato de obra ya existe.")
        nueva_obra = models.Obra(**obra_in.model_dump())
        db.add(nueva_obra)
        db.commit()
        db.refresh(nueva_obra)
        return nueva_obra

    @staticmethod
    def consultar(db: Session, skip: int = 0, limit: int = 100) -> List[models.Obra]:
        return db.query(models.Obra).offset(skip).limit(limit).all()

    @staticmethod
    def obtener_por_id(db: Session, id_obra: int) -> models.Obra:
        obra = db.query(models.Obra).filter(models.Obra.id_obra == id_obra).first()
        if not obra:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obra no encontrada.")
        return obra

    @staticmethod
    def actualizar(db: Session, id_obra: int, obra_in: schemas.ObraUpdate) -> models.Obra:
        obra = ObraService.obtener_por_id(db, id_obra)
        if obra.estado == "CERRADA":
            raise HTTPException(status_code=400, detail="No se puede modificar una obra cerrada.")
        for campo, valor in obra_in.model_dump(exclude_unset=True).items():
            setattr(obra, campo, valor)
        db.commit()
        db.refresh(obra)
        return obra

    @staticmethod
    def cerrar(db: Session, id_obra: int) -> models.Obra:
        obra = ObraService.obtener_por_id(db, id_obra)
        obra.estado = "CERRADA"
        db.commit()
        db.refresh(obra)
        return obra

    @staticmethod
    def registrar_avance_fisico(db: Session, avance_in: schemas.AvanceFisicoCreate) -> models.AvanceFisico:
        ObraService.obtener_por_id(db, avance_in.id_obra)
        nuevo_avance = models.AvanceFisico(**avance_in.model_dump())
        db.add(nuevo_avance)
        db.commit()
        db.refresh(nuevo_avance)
        return nuevo_avance


# ==========================================
# SERVICIO: CONTRATO Y PÓLIZAS
# ==========================================
class ContratoService:
    @staticmethod
    def registrar(db: Session, contrato_in: schemas.ContratoCreate) -> models.Contrato:
        ObraService.obtener_por_id(db, contrato_in.id_obra)
        nuevo_contrato = models.Contrato(**contrato_in.model_dump())
        db.add(nuevo_contrato)
        db.commit()
        db.refresh(nuevo_contrato)
        return nuevo_contrato

    @staticmethod
    def consultar_por_obra(db: Session, id_obra: int) -> List[models.Contrato]:
        return db.query(models.Contrato).filter(models.Contrato.id_obra == id_obra).all()

    @staticmethod
    def actualizar_borrador(db: Session, id_contrato: int, contrato_in: schemas.ContratoUpdate) -> models.Contrato:
        contrato = db.query(models.Contrato).filter(models.Contrato.id_contrato == id_contrato).first()
        if not contrato:
            raise HTTPException(status_code=404, detail="Contrato no encontrado.")
        if contrato.estado != "BORRADOR":
            raise HTTPException(status_code=400, detail="Solo se pueden editar contratos en estado BORRADOR.")
        for campo, valor in contrato_in.model_dump(exclude_unset=True).items():
            setattr(contrato, campo, valor)
        db.commit()
        db.refresh(contrato)
        return contrato

    @staticmethod
    def registrar_poliza(db: Session, poliza_in: schemas.PolizaCreate) -> models.Poliza:
        contrato = db.query(models.Contrato).filter(models.Contrato.id_contrato == poliza_in.id_contrato).first()
        if not contrato:
            raise HTTPException(status_code=404, detail="Contrato no encontrado para asociar la póliza.")
        nueva_poliza = models.Poliza(**poliza_in.model_dump())
        db.add(nueva_poliza)
        db.commit()
        db.refresh(nueva_poliza)
        return nueva_poliza


# ==========================================
# SERVICIO: CATÁLOGO DE CONCEPTOS E INSUMOS
# ==========================================
class CatalogoInsumoService:
    @staticmethod
    def crear_insumo(db: Session, insumo_in: schemas.InsumoCreate) -> models.Insumo:
        ObraService.obtener_por_id(db, insumo_in.id_obra)
        nuevo_insumo = models.Insumo(**insumo_in.model_dump())
        db.add(nuevo_insumo)
        db.commit()
        db.refresh(nuevo_insumo)
        return nuevo_insumo

    @staticmethod
    def consultar_insumos_obra(db: Session, id_obra: int) -> List[models.Insumo]:
        return db.query(models.Insumo).filter(models.Insumo.id_obra == id_obra).all()

    @staticmethod
    def importar_linea_base(db: Session, conceptos_in: List[schemas.ConceptoCatalogoCreate]) -> List[models.ConceptoCatalogo]:
        conceptos_creados = []
        for item in conceptos_in:
            nuevo_concepto = models.ConceptoCatalogo(**item.model_dump())
            db.add(nuevo_concepto)
            conceptos_creados.append(nuevo_concepto)
        db.commit()
        for c in conceptos_creados:
            db.refresh(c)
        return conceptos_creados

    @staticmethod
    def consultar_conceptos_obra(db: Session, id_obra: int) -> List[models.ConceptoCatalogo]:
        return db.query(models.ConceptoCatalogo).filter(models.ConceptoCatalogo.id_obra == id_obra).all()

    @staticmethod
    def editar_antes_del_bloqueo(
        db: Session, id_concepto: int, concepto_in: schemas.ConceptoCatalogoUpdate
    ) -> models.ConceptoCatalogo:
        concepto = db.query(models.ConceptoCatalogo).filter(models.ConceptoCatalogo.id_concepto == id_concepto).first()
        if not concepto:
            raise HTTPException(status_code=404, detail="Concepto no encontrado.")
        if concepto.precio_bloqueado:
            raise HTTPException(status_code=400, detail="El concepto ya tiene el precio bloqueado y no puede editarse.")
        for campo, valor in concepto_in.model_dump(exclude_unset=True).items():
            setattr(concepto, campo, valor)
        db.commit()
        db.refresh(concepto)
        return concepto

    @staticmethod
    def bloquear_precio(db: Session, id_concepto: int) -> models.ConceptoCatalogo:
        concepto = db.query(models.ConceptoCatalogo).filter(models.ConceptoCatalogo.id_concepto == id_concepto).first()
        if not concepto:
            raise HTTPException(status_code=404, detail="Concepto no encontrado.")
        concepto.precio_bloqueado = True
        db.commit()
        db.refresh(concepto)
        return concepto

    @staticmethod
    def crear_concepto_elemento(db: Session, elemento_in: schemas.ConceptoElementoCreate) -> models.ConceptoElemento:
        concepto = db.query(models.ConceptoCatalogo).filter(
            models.ConceptoCatalogo.id_concepto == elemento_in.id_concepto
        ).first()
        if not concepto:
            raise HTTPException(status_code=404, detail="Concepto no encontrado.")
        if concepto.precio_bloqueado:
            raise HTTPException(status_code=400, detail="No se pueden modificar insumos de un concepto bloqueado.")
        nuevo_elemento = models.ConceptoElemento(**elemento_in.model_dump())
        db.add(nuevo_elemento)
        db.commit()
        db.refresh(nuevo_elemento)
        return nuevo_elemento

    @staticmethod
    def actualizar_borrador_elemento(
        db: Session, id_concepto_insumos: int, elemento_in: schemas.ConceptoElementoUpdate
    ) -> models.ConceptoElemento:
        elemento = db.query(models.ConceptoElemento).filter(
            models.ConceptoElemento.id_concepto_insumos == id_concepto_insumos
        ).first()
        if not elemento:
            raise HTTPException(status_code=404, detail="Elemento de concepto no encontrado.")
        for campo, valor in elemento_in.model_dump(exclude_unset=True).items():
            setattr(elemento, campo, valor)
        db.commit()
        db.refresh(elemento)
        return elemento


# ==========================================
# SERVICIO: PROGRAMA DE EJECUCIÓN (GANTT)
# ==========================================
class ProgramaEjecucionService:
    @staticmethod
    def crear(db: Session, prog_in: schemas.ProgramaEjecucionCreate) -> models.ProgramaEjecucion:
        if prog_in.fecha_fin_prog < prog_in.fecha_inicio_prog:
            raise HTTPException(status_code=400, detail="La fecha fin programada no puede ser menor a la de inicio.")
        nueva_act = models.ProgramaEjecucion(**prog_in.model_dump())
        db.add(nueva_act)
        db.commit()
        db.refresh(nueva_act)
        return nueva_act

    @staticmethod
    def consultar_gantt(db: Session, id_obra: int) -> List[models.ProgramaEjecucion]:
        return (
            db.query(models.ProgramaEjecucion)
            .filter(models.ProgramaEjecucion.id_obra == id_obra)
            .order_by(models.ProgramaEjecucion.fecha_inicio_prog.asc())
            .all()
        )

    @staticmethod
    def recalendarizar(
        db: Session, id_actividad: int, prog_in: schemas.ProgramaEjecucionUpdate
    ) -> models.ProgramaEjecucion:
        actividad = db.query(models.ProgramaEjecucion).filter(
            models.ProgramaEjecucion.id_actividad == id_actividad
        ).first()
        if not actividad:
            raise HTTPException(status_code=404, detail="Actividad del programa no encontrada.")
        for campo, valor in prog_in.model_dump(exclude_unset=True).items():
            setattr(actividad, campo, valor)
        db.commit()
        db.refresh(actividad)
        return actividad