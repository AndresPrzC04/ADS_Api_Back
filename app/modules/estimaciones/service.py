from datetime import date
from decimal import Decimal
from typing import List
from fastapi import HTTPException, status
from sqlmodel import Session, select
from app.modules.obras_contratos.models import ConceptoCatalogo
from . import models


# ==========================================
# 1. SERVICIO: TIPO DE ESTIMACIÓN
# ==========================================
class TipoEstimacionService:
    @staticmethod
    def crear(session: Session, tipo_in: models.TipoEstimacionCreate) -> models.TipoEstimacion:
        existente = session.exec(
            select(models.TipoEstimacion).where(models.TipoEstimacion.nombre == tipo_in.nombre)
        ).first()
        if existente:
            raise HTTPException(status_code=400, detail="El tipo de estimación ya existe.")

        nuevo_tipo = models.TipoEstimacion.model_validate(tipo_in)
        session.add(nuevo_tipo)
        session.commit()
        session.refresh(nuevo_tipo)
        return nuevo_tipo

    @staticmethod
    def consultar(session: Session) -> List[models.TipoEstimacion]:
        return session.exec(
            select(models.TipoEstimacion).where(models.TipoEstimacion.activo == True)
        ).all()

    @staticmethod
    def desactivar(session: Session, id_tipo_estimacion: int) -> models.TipoEstimacion:
        tipo = session.get(models.TipoEstimacion, id_tipo_estimacion)
        if not tipo:
            raise HTTPException(status_code=404, detail="Tipo de estimación no encontrado.")
        tipo.activo = False
        session.add(tipo)
        session.commit()
        session.refresh(tipo)
        return tipo


# ==========================================
# 2. SERVICIO: ESTIMACIÓN
# ==========================================
class EstimacionService:
    @staticmethod
    def recalcular_montos(session: Session, estimacion: models.Estimacion) -> None:
        """Suma (cant_ejecutada * precio_unitario) de los generadores y deduce la amortización."""
        generadores = session.exec(
            select(models.Generador).where(models.Generador.id_estimacion == estimacion.id_estimacion)
        ).all()

        total_bruto = Decimal("0.00")
        for gen in generadores:
            concepto = session.get(ConceptoCatalogo, gen.id_concepto)
            if concepto:
                total_bruto += (gen.cant_ejecutada * concepto.precio_unitario)

        estimacion.monto_bruto = total_bruto
        estimacion.monto_neto = max(Decimal("0.00"), total_bruto - estimacion.monto_amortizacion)
        session.add(estimacion)
        session.commit()
        session.refresh(estimacion)

    @staticmethod
    def crear_borrador(session: Session, estimacion_in: models.EstimacionCreate) -> models.Estimacion:
        if estimacion_in.periodo_fin < estimacion_in.periodo_inicio:
            raise HTTPException(status_code=400, detail="La fecha fin del periodo no puede ser menor a la de inicio.")

        nueva_estimacion = models.Estimacion.model_validate(estimacion_in)
        nueva_estimacion.estado = "BORRADOR"
        session.add(nueva_estimacion)
        session.commit()
        session.refresh(nueva_estimacion)
        return nueva_estimacion

    @staticmethod
    def obtener_por_id(session: Session, id_estimacion: int) -> models.Estimacion:
        estimacion = session.get(models.Estimacion, id_estimacion)
        if not estimacion:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estimación no encontrada.")
        return estimacion

    @staticmethod
    def consultar_por_obra(session: Session, id_obra: int) -> List[models.Estimacion]:
        return session.exec(
            select(models.Estimacion)
            .where(models.Estimacion.id_obra == id_obra)
            .order_by(models.Estimacion.numero_estimacion.asc())
        ).all()

    @staticmethod
    def eliminar_borrador(session: Session, id_estimacion: int) -> dict:
        estimacion = EstimacionService.obtener_por_id(session, id_estimacion)
        if estimacion.estado != "BORRADOR":
            raise HTTPException(
                status_code=400,
                detail="Solo se pueden eliminar estimaciones que se encuentren en estado BORRADOR."
            )
        session.delete(estimacion)
        session.commit()
        return {"detalle": f"Estimación {id_estimacion} eliminada correctamente."}

    @staticmethod
    def enviar_revision(session: Session, id_estimacion: int) -> models.Estimacion:
        estimacion = EstimacionService.obtener_por_id(session, id_estimacion)
        if estimacion.estado not in ["BORRADOR", "RECHAZADA"]:
            raise HTTPException(status_code=400, detail="La estimación no se encuentra en estado apto para revisión.")

        generadores = session.exec(
            select(models.Generador).where(models.Generador.id_estimacion == id_estimacion)
        ).all()
        if not generadores:
            raise HTTPException(status_code=400, detail="No se puede enviar a revisión una estimación sin generadores.")

        EstimacionService.recalcular_montos(session, estimacion)
        estimacion.estado = "EN_REVISION"
        session.add(estimacion)
        session.commit()
        session.refresh(estimacion)
        return estimacion

    @staticmethod
    def autorizar_pago(session: Session, id_estimacion: int) -> models.Estimacion:
        estimacion = EstimacionService.obtener_por_id(session, id_estimacion)
        if estimacion.estado != "APROBADA":
            raise HTTPException(
                status_code=400,
                detail="La estimación debe estar previamente APROBADA por el supervisor para autorizar su pago."
            )
        estimacion.estado = "AUTORIZADA_PAGO"
        session.add(estimacion)
        session.commit()
        session.refresh(estimacion)
        return estimacion


# ==========================================
# 3. SERVICIO: GENERADORES Y VALIDACIÓN
# ==========================================
class GeneradorService:
    @staticmethod
    def crear(session: Session, gen_in: models.GeneradorCreate) -> models.Generador:
        estimacion = EstimacionService.obtener_por_id(session, gen_in.id_estimacion)
        if estimacion.estado not in ["BORRADOR", "RECHAZADA"]:
            raise HTTPException(status_code=400, detail="No se pueden registrar generadores en una estimación bloqueada.")

        concepto = session.get(ConceptoCatalogo, gen_in.id_concepto)
        if not concepto:
            raise HTTPException(status_code=404, detail="El concepto de catálogo indicado no existe.")

        nuevo_gen = models.Generador.model_validate(gen_in)
        session.add(nuevo_gen)
        session.commit()
        session.refresh(nuevo_gen)

        EstimacionService.recalcular_montos(session, estimacion)
        return nuevo_gen

    @staticmethod
    def consultar_por_estimacion(session: Session, id_estimacion: int) -> List[models.Generador]:
        return session.exec(
            select(models.Generador).where(models.Generador.id_estimacion == id_estimacion)
        ).all()

    @staticmethod
    def corregir_borrador(
        session: Session, id_generador: int, gen_in: models.GeneradorUpdate
    ) -> models.Generador:
        generador = session.get(models.Generador, id_generador)
        if not generador:
            raise HTTPException(status_code=404, detail="Generador no encontrado.")

        estimacion = EstimacionService.obtener_por_id(session, generador.id_estimacion)
        if estimacion.estado not in ["BORRADOR", "RECHAZADA"]:
            raise HTTPException(status_code=400, detail="Solo se pueden editar generadores en estado BORRADOR o RECHAZADA.")

        datos = gen_in.model_dump(exclude_unset=True)
        for campo, valor in datos.items():
            setattr(generador, campo, valor)

        session.add(generador)
        session.commit()
        session.refresh(generador)

        EstimacionService.recalcular_montos(session, estimacion)
        return generador

    @staticmethod
    def registrar_dictamen_validacion(
        session: Session, val_in: models.GeneradorValidacionCreate
    ) -> models.GeneradorValidacion:
        generador = session.get(models.Generador, val_in.id_generador)
        if not generador:
            raise HTTPException(status_code=404, detail="Generador no encontrado para validar.")

        nueva_val = models.GeneradorValidacion.model_validate(val_in)
        session.add(nueva_val)
        session.commit()
        session.refresh(nueva_val)
        return nueva_val


# ==========================================
# 4. SERVICIO: REVISIÓN DE ESTIMACIONES
# ==========================================
class RevisionEstimacionService:
    @staticmethod
    def emitir_dictamen(
        session: Session, rev_in: models.RevisionEstimacionCreate
    ) -> models.RevisionEstimacion:
        EstimacionService.obtener_por_id(session, rev_in.id_estimacion)
        nueva_rev = models.RevisionEstimacion.model_validate(rev_in)
        session.add(nueva_rev)
        session.commit()
        session.refresh(nueva_rev)
        return nueva_rev

    @staticmethod
    def aprobar(
        session: Session, id_revision: int, monto_autorizado_neto: Decimal
    ) -> models.RevisionEstimacion:
        revision = session.get(models.RevisionEstimacion, id_revision)
        if not revision:
            raise HTTPException(status_code=404, detail="Registro de revisión no encontrado.")

        revision.estatus_revision = "APROBADA"
        revision.monto_autorizado_neto = monto_autorizado_neto
        revision.fecha_autorizacion = date.today()

        estimacion = EstimacionService.obtener_por_id(session, revision.id_estimacion)
        estimacion.estado = "APROBADA"
        estimacion.monto_neto = monto_autorizado_neto

        session.add(revision)
        session.add(estimacion)
        session.commit()
        session.refresh(revision)
        return revision

    @staticmethod
    def rechazar(session: Session, id_revision: int) -> models.RevisionEstimacion:
        revision = session.get(models.RevisionEstimacion, id_revision)
        if not revision:
            raise HTTPException(status_code=404, detail="Registro de revisión no encontrado.")

        revision.estatus_revision = "RECHAZADA"
        estimacion = EstimacionService.obtener_por_id(session, revision.id_estimacion)
        estimacion.estado = "RECHAZADA"

        session.add(revision)
        session.add(estimacion)
        session.commit()
        session.refresh(revision)
        return revision

    @staticmethod
    def consultar_por_estimacion(session: Session, id_estimacion: int) -> List[models.RevisionEstimacion]:
        return session.exec(
            select(models.RevisionEstimacion).where(models.RevisionEstimacion.id_estimacion == id_estimacion)
        ).all()


# ==========================================
# 5. SERVICIO: FACTURACIÓN ESTIMACIÓN (CFDI)
# ==========================================
class FacturacionEstimacionService:
    @staticmethod
    def adjuntar_fiscal(
        session: Session, factura_in: models.FacturacionEstimacionCreate
    ) -> models.FacturacionEstimacion:
        estimacion = EstimacionService.obtener_por_id(session, factura_in.id_estimacion)
        if estimacion.estado not in ["APROBADA", "AUTORIZADA_PAGO"]:
            raise HTTPException(
                status_code=400,
                detail="Solo se puede cargar factura fiscal a una estimación APROBADA o AUTORIZADA_PAGO."
            )

        existente = session.exec(
            select(models.FacturacionEstimacion).where(
                models.FacturacionEstimacion.id_estimacion == factura_in.id_estimacion
            )
        ).first()
        if existente:
            raise HTTPException(status_code=400, detail="La estimación ya cuenta con comprobante fiscal cargado.")

        nueva_factura = models.FacturacionEstimacion.model_validate(factura_in)
        session.add(nueva_factura)
        session.commit()
        session.refresh(nueva_factura)
        return nueva_factura

    @staticmethod
    def consultar_por_estimacion(session: Session, id_estimacion: int) -> models.FacturacionEstimacion:
        factura = session.exec(
            select(models.FacturacionEstimacion).where(
                models.FacturacionEstimacion.id_estimacion == id_estimacion
            )
        ).first()
        if not factura:
            raise HTTPException(status_code=404, detail="No se encontró comprobante fiscal para esta estimación.")
        return factura