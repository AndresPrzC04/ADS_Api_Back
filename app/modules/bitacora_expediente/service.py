from typing import List
from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.modules.obras_contratos.models import Obra
from app.modules.usuarios_accesos.service import AuditoriaService
from app.modules.usuarios_accesos.schemas import AuditoriaLogCreate
from . import models, schemas


# ==========================================
# 1. SERVICIO: BITÁCORA DE OBRA (Inmutable)
# ==========================================
class BitacoraService:
    @staticmethod
    def crear(db: Session, nota_in: schemas.BitacoraNotaCreate) -> models.BitacoraNota:
        # 1. Verificar si la bitácora de esta obra ya fue cerrada
        nota_cierre = db.query(models.BitacoraNota).filter(
            models.BitacoraNota.id_obra == nota_in.id_obra,
            models.BitacoraNota.tipo_nota == "CIERRE"
        ).first()
        if nota_cierre:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La bitácora de esta obra ya cuenta con nota de CIERRE y no admite nuevos registros."
            )

        # 2. Calcular automáticamente el consecutivo_nota por obra
        ultimo_consecutivo = db.query(func.max(models.BitacoraNota.consecutivo_nota)).filter(
            models.BitacoraNota.id_obra == nota_in.id_obra
        ).scalar() or 0

        if ultimo_consecutivo == 0 and nota_in.tipo_nota.upper() != "APERTURA":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La primera nota (consecutivo 1) de toda obra debe ser obligatoriamente de tipo APERTURA."
            )

        nueva_nota = models.BitacoraNota(
            **nota_in.model_dump(),
            consecutivo_nota=ultimo_consecutivo + 1,
            firmada=False
        )
        nueva_nota.tipo_nota = nueva_nota.tipo_nota.upper()
        db.add(nueva_nota)
        db.commit()
        db.refresh(nueva_nota)

        # 3. Registrar evento en AuditoriaLog
        AuditoriaService.registrar_evento(
            db,
            AuditoriaLogCreate(
                id_usuario=nota_in.id_usuario,
                id_obra=nota_in.id_obra,
                accion_ejecutada=f"CREACION_NOTA_BITACORA #{nueva_nota.consecutivo_nota} ({nueva_nota.tipo_nota})",
                tabla_afectada="bitacora_notas",
                registro_id=nueva_nota.id_nota
            )
        )
        return nueva_nota

    @staticmethod
    def consultar_paginado(
        db: Session, id_obra: int, skip: int = 0, limit: int = 50
    ) -> List[models.BitacoraNota]:
        return (
            db.query(models.BitacoraNota)
            .filter(models.BitacoraNota.id_obra == id_obra)
            .order_by(models.BitacoraNota.consecutivo_nota.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    @staticmethod
    def firmar(
        db: Session, id_nota: int, firma_in: schemas.BitacoraNotaFirma
    ) -> models.BitacoraNota:
        nota = db.query(models.BitacoraNota).filter(models.BitacoraNota.id_nota == id_nota).first()
        if not nota:
            raise HTTPException(status_code=404, detail="Nota de bitácora no encontrada.")
        if nota.firmada:
            raise HTTPException(status_code=400, detail="Esta nota ya fue firmada previamente y es inalterable.")

        nota.firmada = True
        nota.sello_digital = firma_in.sello_digital
        db.commit()
        db.refresh(nota)

        AuditoriaService.registrar_evento(
            db,
            AuditoriaLogCreate(
                id_usuario=nota.id_usuario,
                id_obra=nota.id_obra,
                accion_ejecutada=f"FIRMA_ELECTRONICA_NOTA #{nota.consecutivo_nota}",
                tabla_afectada="bitacora_notas",
                registro_id=nota.id_nota
            )
        )
        return nota

    @staticmethod
    def cerrar_bitacora(
        db: Session, id_obra: int, id_residente_usuario: int, descripcion_cierre: str
    ) -> models.BitacoraNota:
        """Emite la nota final de cierre y bloquea futuras inserciones en la bitácora."""
        nota_cierre_in = schemas.BitacoraNotaCreate(
            id_obra=id_obra,
            id_usuario=id_residente_usuario,
            tipo_nota="CIERRE",
            asunto="CIERRE DEFINITIVO DE BITÁCORA ELECTRÓNICA DE OBRA",
            descripcion=descripcion_cierre
        )
        return BitacoraService.crear(db, nota_cierre_in)


# ==========================================
# 2. SERVICIO: EXPEDIENTE DOCUMENTAL
# ==========================================
class ExpedienteDocumentoService:
    @staticmethod
    def subir(db: Session, doc_in: schemas.ExpedienteDocumentoCreate) -> models.ExpedienteDocumento:
        obra = db.query(Obra).filter(Obra.id_obra == doc_in.id_obra).first()
        if not obra:
            raise HTTPException(status_code=404, detail="La obra especificada no existe.")

        nuevo_doc = models.ExpedienteDocumento(**doc_in.model_dump())
        db.add(nuevo_doc)
        db.commit()
        db.refresh(nuevo_doc)
        return nuevo_doc

    @staticmethod
    def consultar_por_obra(db: Session, id_obra: int) -> List[models.ExpedienteDocumento]:
        return (
            db.query(models.ExpedienteDocumento)
            .filter(models.ExpedienteDocumento.id_obra == id_obra)
            .order_by(models.ExpedienteDocumento.fase.asc(), models.ExpedienteDocumento.version.desc())
            .all()
        )

    @staticmethod
    def actualizar(
        db: Session, id_documento: int, doc_in: schemas.ExpedienteDocumentoUpdate
    ) -> models.ExpedienteDocumento:
        doc = db.query(models.ExpedienteDocumento).filter(
            models.ExpedienteDocumento.id_documento == id_documento
        ).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Documento de expediente no encontrado.")
        for campo, valor in doc_in.model_dump(exclude_unset=True).items():
            setattr(doc, campo, valor)
        db.commit()
        db.refresh(doc)
        return doc

    @staticmethod
    def eliminar(db: Session, id_documento: int) -> dict:
        doc = db.query(models.ExpedienteDocumento).filter(
            models.ExpedienteDocumento.id_documento == id_documento
        ).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Documento no encontrado.")
        if doc.estatus == "APROBADO":
            raise HTTPException(
                status_code=400,
                detail="No se puede eliminar un documento que ya ha sido APROBADO en el expediente oficial."
            )
        db.delete(doc)
        db.commit()
        return {"detalle": f"Documento {id_documento} eliminado correctamente."}


# ==========================================
# 3. SERVICIO: ARCHIVOS ADJUNTOS (Polimórfico)
# ==========================================
class ArchivoAdjuntoService:
    @staticmethod
    def agregar(db: Session, adjunto_in: schemas.ArchivoAdjuntoCreate) -> models.ArchivoAdjunto:
        nuevo_adjunto = models.ArchivoAdjunto(**adjunto_in.model_dump())
        db.add(nuevo_adjunto)
        db.commit()
        db.refresh(nuevo_adjunto)
        return nuevo_adjunto

    @staticmethod
    def consultar_por_entidad(
        db: Session, entidad_tipo: str, entidad_id: int
    ) -> List[models.ArchivoAdjunto]:
        return (
            db.query(models.ArchivoAdjunto)
            .filter(
                models.ArchivoAdjunto.entidad_tipo == entidad_tipo.upper(),
                models.ArchivoAdjunto.entidad_id == entidad_id
            )
            .all()
        )

    @staticmethod
    def eliminar(db: Session, id_archivo_adjunto: int) -> dict:
        adjunto = db.query(models.ArchivoAdjunto).filter(
            models.ArchivoAdjunto.id_archivo_adjunto == id_archivo_adjunto
        ).first()
        if not adjunto:
            raise HTTPException(status_code=404, detail="Archivo adjunto no encontrado.")

        # Si pertenece a una nota de bitácora ya firmada, prohibir su eliminación
        if adjunto.entidad_tipo == "BITACORA":
            nota = db.query(models.BitacoraNota).filter(
                models.BitacoraNota.id_nota == adjunto.entidad_id
            ).first()
            if nota and nota.firmada:
                raise HTTPException(
                    status_code=400,
                    detail="No se puede eliminar evidencia adjunta de una nota de bitácora ya firmada."
                )

        db.delete(adjunto)
        db.commit()
        return {"detalle": f"Archivo adjunto {id_archivo_adjunto} eliminado."}


# ==========================================
# 4. SERVICIO: CONTROL DE CALIDAD Y REPORTES
# ==========================================
class SupervisionCalidadService:
    @staticmethod
    def registrar_ensayo(
        db: Session, prueba_in: schemas.ControlCalidadPruebaCreate
    ) -> models.ControlCalidadPrueba:
        nueva_prueba = models.ControlCalidadPrueba(**prueba_in.model_dump())
        db.add(nueva_prueba)
        db.commit()
        db.refresh(nueva_prueba)
        return nueva_prueba

    @staticmethod
    def consultar_ensayos_obra(db: Session, id_obra: int) -> List[models.ControlCalidadPrueba]:
        return db.query(models.ControlCalidadPrueba).filter(
            models.ControlCalidadPrueba.id_obra == id_obra
        ).all()

    @staticmethod
    def crear_reporte_diario(
        db: Session, reporte_in: schemas.ReporteDiarioSupervisionCreate
    ) -> models.ReporteDiarioSupervision:
        nuevo_reporte = models.ReporteDiarioSupervision(**reporte_in.model_dump())
        db.add(nuevo_reporte)
        db.commit()
        db.refresh(nuevo_reporte)
        return nuevo_reporte

    @staticmethod
    def consultar_reportes_diarios(db: Session, id_obra: int) -> List[models.ReporteDiarioSupervision]:
        return (
            db.query(models.ReporteDiarioSupervision)
            .filter(models.ReporteDiarioSupervision.id_obra == id_obra)
            .order_by(models.ReporteDiarioSupervision.fecha_reporte.desc())
            .all()
        )