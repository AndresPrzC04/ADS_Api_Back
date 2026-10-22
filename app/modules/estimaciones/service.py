from datetime import date
from decimal import Decimal
from typing import List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.modules.obras_contratos.models import ConceptoCatalogo
from . import models, schemas


# ==========================================
# 1. SERVICIO: TIPO DE ESTIMACIÓN
# ==========================================
class TipoEstimacionService:
    @staticmethod
    def crear(db: Session, tipo_in: schemas.TipoEstimacionCreate) -> models.TipoEstimacion:
        existente = db.query(models.TipoEstimacion).filter(
            models.TipoEstimacion.nombre == tipo_in.nombre
        ).first()
        if existente:
            raise HTTPException(status_code=400, detail="El tipo de estimación ya existe.")
        nuevo_tipo = models.TipoEstimacion(**tipo_in.model_dump())
        db.add(nuevo_tipo)
        db.commit()
        db.refresh(nuevo_tipo)
        return nuevo_tipo

    @staticmethod
    def consultar(db: Session) -> List[models.TipoEstimacion]:
        return db.query(models.TipoEstimacion).filter(models.TipoEstimacion.activo == True).all()

    @staticmethod
    def desactivar(db: Session, id_tipo_estimacion: int) -> models.TipoEstimacion:
        tipo = db.query(models.TipoEstimacion).filter(
            models.TipoEstimacion.id_tipo_estimacion == id_tipo_estimacion
        ).first()
        if not tipo:
            raise HTTPException(status_code=404, detail="Tipo de estimación no encontrado.")
        tipo.activo = False
        db.commit()
        db.refresh(tipo)
        return tipo


# ==========================================
# 2. SERVICIO: ESTIMACIÓN (Ciclo de vida)
# ==========================================
class EstimacionService:
    @staticmethod
    def recalcular_montos(db: Session, estimacion: models.Estimacion) -> None:
        """Recalcula el monto bruto y neto sumando (cant_ejecutada * precio_unitario) de sus generadores."""
        total_bruto = Decimal("0.00")
        for gen in estimacion.generadores:
            concepto = db.query(ConceptoCatalogo).filter(
                ConceptoCatalogo.id_concepto == gen.id_concepto
            ).first()
            if concepto:
                total_bruto += (gen.cant_ejecutada * concepto.precio_unitario)

        estimacion.monto_bruto = total_bruto
        estimacion.monto_neto = max(Decimal("0.00"), total_bruto - estimacion.monto_amortizacion)
        db.commit()
        db.refresh(estimacion)

    @staticmethod
    def crear_borrador(db: Session, estimacion_in: schemas.EstimacionCreate) -> models.Estimacion:
        if estimacion_in.periodo_fin < estimacion_in.periodo_inicio:
            raise HTTPException(status_code=400, detail="La fecha fin del periodo no puede ser menor a la de inicio.")

        nueva_estimacion = models.Estimacion(
            **estimacion_in.model_dump(),
            estado="BORRADOR"
        )
        db.add(nueva_estimacion)
        db.commit()
        db.refresh(nueva_estimacion)
        return nueva_estimacion

    @staticmethod
    def obtener_por_id(db: Session, id_estimacion: int) -> models.Estimacion:
        estimacion = db.query(models.Estimacion).filter(
            models.Estimacion.id_estimacion == id_estimacion
        ).first()
        if not estimacion:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estimación no encontrada.")
        return estimacion

    @staticmethod
    def consultar_por_obra(db: Session, id_obra: int) -> List[models.Estimacion]:
        return (
            db.query(models.Estimacion)
            .filter(models.Estimacion.id_obra == id_obra)
            .order_by(models.Estimacion.numero_estimacion.asc())
            .all()
        )

    @staticmethod
    def eliminar_borrador(db: Session, id_estimacion: int) -> dict:
        estimacion = EstimacionService.obtener_por_id(db, id_estimacion)
        if estimacion.estado != "BORRADOR":
            raise HTTPException(
                status_code=400,
                detail="Solo se pueden eliminar estimaciones que se encuentren en estado BORRADOR."
            )
        db.delete(estimacion)
        db.commit()
        return {"detalle": f"Estimación {id_estimacion} en borrador eliminada correctamente."}

    @staticmethod
    def enviar_revision(db: Session, id_estimacion: int) -> models.Estimacion:
        estimacion = EstimacionService.obtener_por_id(db, id_estimacion)
        if estimacion.estado not in ["BORRADOR", "RECHAZADA"]:
            raise HTTPException(status_code=400, detail="La estimación no está en un estado válido para enviarse a revisión.")
        if not estimacion.generadores:
            raise HTTPException(status_code=400, detail="No se puede enviar a revisión una estimación sin generadores adjuntos.")
        
        EstimacionService.recalcular_montos(db, estimacion)
        estimacion.estado = "EN_REVISION"
        db.commit()
        db.refresh(estimacion)
        return estimacion

    @staticmethod
    def autorizar_pago(db: Session, id_estimacion: int) -> models.Estimacion:
        """Acción ejecutada por el Residente una vez aprobada por la Supervisión."""
        estimacion = EstimacionService.obtener_por_id(db, id_estimacion)
        if estimacion.estado != "APROBADA":
            raise HTTPException(
                status_code=400,
                detail="La estimación debe estar previamente APROBADA por la supervisión técnica."
            )
        estimacion.estado = "AUTORIZADA_PAGO"
        db.commit()
        db.refresh(estimacion)
        return estimacion


# ==========================================
# 3. SERVICIO: GENERADORES Y VALIDACIÓN
# ==========================================
class GeneradorService:
    @staticmethod
    def crear(db: Session, gen_in: schemas.GeneradorCreate) -> models.Generador:
        estimacion = EstimacionService.obtener_por_id(db, gen_in.id_estimacion)
        if estimacion.estado not in ["BORRADOR", "RECHAZADA"]:
            raise HTTPException(status_code=400, detail="No se pueden agregar generadores a una estimación bloqueada.")

        concepto = db.query(ConceptoCatalogo).filter(ConceptoCatalogo.id_concepto == gen_in.id_concepto).first()
        if not concepto:
            raise HTTPException(status_code=404, detail="El concepto del catálogo especificado no existe.")

        nuevo_gen = models.Generador(**gen_in.model_dump())
        db.add(nuevo_gen)
        db.commit()
        db.refresh(nuevo_gen)

        EstimacionService.recalcular_montos(db, estimacion)
        return nuevo_gen

    @staticmethod
    def consultar_por_estimacion(db: Session, id_estimacion: int) -> List[models.Generador]:
        return db.query(models.Generador).filter(models.Generador.id_estimacion == id_estimacion).all()

    @staticmethod
    def corregir_borrador(db: Session, id_generador: int, gen_in: schemas.GeneradorUpdate) -> models.Generador:
        generador = db.query(models.Generador).filter(models.Generador.id_generador == id_generador).first()
        if not generador:
            raise HTTPException(status_code=404, detail="Generador no encontrado.")

        estimacion = EstimacionService.obtener_por_id(db, generador.id_estimacion)
        if estimacion.estado not in ["BORRADOR", "RECHAZADA"]:
            raise HTTPException(status_code=400, detail="Solo se pueden corregir generadores en estado BORRADOR o RECHAZADA.")

        for campo, valor in gen_in.model_dump(exclude_unset=True).items():
            setattr(generador, campo, valor)
        db.commit()
        db.refresh(generador)

        EstimacionService.recalcular_montos(db, estimacion)
        return generador

    @staticmethod
    def registrar_dictamen_validacion(
        db: Session, val_in: schemas.GeneradorValidacionCreate
    ) -> models.GeneradorValidacion:
        generador = db.query(models.Generador).filter(models.Generador.id_generador == val_in.id_generador).first()
        if not generador:
            raise HTTPException(status_code=404, detail="Generador no encontrado para validar.")

        nueva_val = models.GeneradorValidacion(**val_in.model_dump())
        db.add(nueva_val)
        db.commit()
        db.refresh(nueva_val)
        return nueva_val


# ==========================================
# 4. SERVICIO: REVISIÓN DE ESTIMACIONES
# ==========================================
class RevisionEstimacionService:
    @staticmethod
    def emitir_dictamen(db: Session, rev_in: schemas.RevisionEstimacionCreate) -> models.RevisionEstimacion:
        estimacion = EstimacionService.obtener_por_id(db, rev_in.id_estimacion)
        nueva_rev = models.RevisionEstimacion(**rev_in.model_dump())
        db.add(nueva_rev)
        db.commit()
        db.refresh(nueva_rev)
        return nueva_rev

    @staticmethod
    def aprobar(db: Session, id_revision: int, monto_autorizado_neto: Decimal) -> models.RevisionEstimacion:
        revision = db.query(models.RevisionEstimacion).filter(
            models.RevisionEstimacion.id_revision == id_revision
        ).first()
        if not revision:
            raise HTTPException(status_code=404, detail="Registro de revisión no encontrado.")

        revision.estatus_revision = "APROBADA"
        revision.monto_autorizado_neto = monto_autorizado_neto
        revision.fecha_autorizacion = date.today()

        estimacion = EstimacionService.obtener_por_id(db, revision.id_estimacion)
        estimacion.estado = "APROBADA"
        estimacion.monto_neto = monto_autorizado_neto

        db.commit()
        db.refresh(revision)
        return revision

    @staticmethod
    def rechazar(db: Session, id_revision: int) -> models.RevisionEstimacion:
        revision = db.query(models.RevisionEstimacion).filter(
            models.RevisionEstimacion.id_revision == id_revision
        ).first()
        if not revision:
            raise HTTPException(status_code=404, detail="Registro de revisión no encontrado.")

        revision.estatus_revision = "RECHAZADA"
        estimacion = EstimacionService.obtener_por_id(db, revision.id_estimacion)
        estimacion.estado = "RECHAZADA"

        db.commit()
        db.refresh(revision)
        return revision

    @staticmethod
    def consultar_por_estimacion(db: Session, id_estimacion: int) -> List[models.RevisionEstimacion]:
        return db.query(models.RevisionEstimacion).filter(
            models.RevisionEstimacion.id_estimacion == id_estimacion
        ).all()


# ==========================================
# 5. SERVICIO: FACTURACIÓN ESTIMACIÓN
# ==========================================
class FacturacionEstimacionService:
    @staticmethod
    def adjuntar_fiscal(db: Session, factura_in: schemas.FacturacionEstimacionCreate) -> models.FacturacionEstimacion:
        estimacion = EstimacionService.obtener_por_id(db, factura_in.id_estimacion)
        if estimacion.estado not in ["APROBADA", "AUTORIZADA_PAGO"]:
            raise HTTPException(
                status_code=400,
                detail="Solo se puede adjuntar factura a una estimación aprobada o autorizada para pago."
            )
        if db.query(models.FacturacionEstimacion).filter(
            models.FacturacionEstimacion.id_estimacion == factura_in.id_estimacion
        ).first():
            raise HTTPException(status_code=400, detail="Esta estimación ya cuenta con una factura asociada.")

        nueva_factura = models.FacturacionEstimacion(**factura_in.model_dump())
        db.add(nueva_factura)
        db.commit()
        db.refresh(nueva_factura)
        return nueva_factura

    @staticmethod
    def consultar_por_estimacion(db: Session, id_estimacion: int) -> models.FacturacionEstimacion:
        factura = db.query(models.FacturacionEstimacion).filter(
            models.FacturacionEstimacion.id_estimacion == id_estimacion
        ).first()
        if not factura:
            raise HTTPException(status_code=404, detail="No hay factura registrada para esta estimación.")
        return factura