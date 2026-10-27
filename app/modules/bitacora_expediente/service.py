from typing import List
from fastapi import HTTPException, status
from sqlalchemy import func
from sqlmodel import Session, select
from app.modules.obras_contratos.models import Obra
from app.modules.usuarios_accesos.service import AuditoriaService
from app.modules.usuarios_accesos.models import AuditoriaLogCreate
from . import models


# ==========================================
# 1. SERVICIO: BITÁCORA DE OBRA (Inmutable)
# ==========================================
class BitacoraService:
    @staticmethod
    def crear(session: Session, nota_in: models.BitacoraNotaCreate) -> models.BitacoraNota:
        # 1. Verificar que la bitácora no esté cerrada
        nota_cierre = session.exec(
            select(models.BitacoraNota).where(
                models.BitacoraNota.id_obra == nota_in.id_obra,
                models.BitacoraNota.tipo_nota == "CIERRE"
            )
        ).first()
        if nota_cierre:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La bitácora de esta obra ya cuenta con nota de CIERRE y es inmutable."
            )

        # 2. Calcular consecutivo_nota por obra
        ultimo_consecutivo = session.exec(
            select(func.max(models.BitacoraNota.consecutivo_nota)).where(
                models.BitacoraNota.id_obra == nota_in.id_obra
            )
        ).one() or 0

        tipo_normalizado = nota_in.tipo_nota.upper()
        if ultimo_consecutivo == 0 and tipo_normalizado != "APERTURA":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La primera nota (consecutivo 1) debe ser obligatoriamente de tipo APERTURA."
            )

        nueva_nota = models.BitacoraNota(
            **nota_in.model_dump(),
            consecutivo_nota=ultimo_consecutivo + 1,
            firmada=False
        )
        nueva_nota.tipo_nota = tipo_normalizado
        session.add(nueva_nota)
        session.commit()
        session.refresh(nueva_nota)

        # 3. Registro en AuditoriaLog
        AuditoriaService.registrar_evento(
            session,
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
        session: Session, id_obra: int, skip: int = 0, limit: int = 50
    ) -> List[models.BitacoraNota]:
        return session.exec(
            select(models.BitacoraNota)
            .where(models.BitacoraNota.id_obra == id_obra)
            .order_by(models.BitacoraNota.consecutivo_nota.asc())
            .offset(skip)
            .limit(limit)
        ).all()

    @staticmethod
    def firmar(
        session: Session, id_nota: int, firma_in: models.BitacoraNotaFirma
    ) -> models.BitacoraNota:
        nota = session.get(models.BitacoraNota, id_nota)
        if not nota:
            raise HTTPException(status_code=404, detail="Nota de bitácora no encontrada.")
        if nota.firmada:
            raise HTTPException(status_code=400, detail="Esta nota ya fue firmada y no puede alterarse.")

        nota.firmada = True
        nota.sello_digital = firma_in.sello_digital
        session.add(nota)
        session.commit()
        session.refresh(nota)

        AuditoriaService.registrar_evento(
            session,
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
        session: Session, id_obra: int, id_residente_usuario: int, descripcion_cierre: str
    ) -> models.BitacoraNota:
        nota_cierre_in = models.BitacoraNotaCreate(
            id_obra=id_obra,
            id_usuario=id_residente_usuario,
            tipo_nota="CIERRE",
            asunto="CIERRE DEFINITIVO DE BITÁCORA ELECTRÓNICA DE OBRA",
            descripcion=descripcion_cierre
        )
        return BitacoraService.crear(session, nota_cierre_in)


# ==========================================
# 2. SERVICIO: EXPEDIENTE DOCUMENTAL
# ==========================================
class ExpedienteDocumentoService:
    @staticmethod
    def subir(session: Session, doc_in: models.ExpedienteDocumentoCreate) -> models.ExpedienteDocumento:
        obra = session.get(Obra, doc_in.id_obra)
        if not obra:
            raise HTTPException(status_code=404, detail="La obra especificada no existe.")

        nuevo_doc = models.ExpedienteDocumento.model_validate(doc_in)
        session.add(nuevo_doc)
        session.commit()
        session.refresh(nuevo_doc)
        return nuevo_doc

    @staticmethod
    def consultar_por_obra(session: Session, id_obra: int) -> List[models.ExpedienteDocumento]:
        return session.exec(
            select(models.ExpedienteDocumento)
            .where(models.ExpedienteDocumento.id_obra == id_obra)
            .order_by(models.ExpedienteDocumento.fase.asc(), models.ExpedienteDocumento.version.desc())
        ).all()

    @staticmethod
    def actualizar(
        session: Session, id_documento: int, doc_in: models.ExpedienteDocumentoUpdate
    ) -> models.ExpedienteDocumento:
        doc = session.get(models.ExpedienteDocumento, id_documento)
        if not doc:
            raise HTTPException(status_code=404, detail="Documento de expediente no encontrado.")

        datos = doc_in.model_dump(exclude_unset=True)
        for campo, valor in datos.items():
            setattr(doc, campo, valor)

        session.add(doc)
        session.commit()
        session.refresh(doc)
        return doc

    @staticmethod
    def eliminar(session: Session, id_documento: int) -> dict:
        doc = session.get(models.ExpedienteDocumento, id_documento)
        if not doc:
            raise HTTPException(status_code=404, detail="Documento no encontrado.")
        if doc.estatus == "APROBADO":
            raise HTTPException(
                status_code=400,
                detail="No se puede eliminar un documento que ya ha sido APROBADO en el expediente."
            )
        session.delete(doc)
        session.commit()
        return {"detalle": f"Documento {id_documento} eliminado correctamente."}


# ==========================================
# 3. SERVICIO: ARCHIVOS ADJUNTOS (Polimórfico)
# ==========================================
class ArchivoAdjuntoService:
    @staticmethod
    def agregar(session: Session, adjunto_in: models.ArchivoAdjuntoCreate) -> models.ArchivoAdjunto:
        nuevo_adjunto = models.ArchivoAdjunto.model_validate(adjunto_in)
        nuevo_adjunto.entidad_tipo = nuevo_adjunto.entidad_tipo.upper()
        session.add(nuevo_adjunto)
        session.commit()
        session.refresh(nuevo_adjunto)
        return nuevo_adjunto

    @staticmethod
    def consultar_por_entidad(
        session: Session, entidad_tipo: str, entidad_id: int
    ) -> List[models.ArchivoAdjunto]:
        return session.exec(
            select(models.ArchivoAdjunto).where(
                models.ArchivoAdjunto.entidad_tipo == entidad_tipo.upper(),
                models.ArchivoAdjunto.entidad_id == entidad_id
            )
        ).all()

    @staticmethod
    def eliminar(session: Session, id_archivo_adjunto: int) -> dict:
        adjunto = session.get(models.ArchivoAdjunto, id_archivo_adjunto)
        if not adjunto:
            raise HTTPException(status_code=404, detail="Archivo adjunto no encontrado.")

        if adjunto.entidad_tipo == "BITACORA":
            nota = session.get(models.BitacoraNota, adjunto.entidad_id)
            if nota and nota.firmada:
                raise HTTPException(
                    status_code=400,
                    detail="Prohibido eliminar evidencias adjuntas de una nota de bitácora ya firmada."
                )

        session.delete(adjunto)
        session.commit()
        return {"detalle": f"Archivo adjunto {id_archivo_adjunto} eliminado."}


# ==========================================
# 4. SERVICIO: CONTROL DE CALIDAD Y REPORTES
# ==========================================
class SupervisionCalidadService:
    @staticmethod
    def registrar_ensayo(
        session: Session, prueba_in: models.ControlCalidadPruebaCreate
    ) -> models.ControlCalidadPrueba:
        nueva_prueba = models.ControlCalidadPrueba.model_validate(prueba_in)
        session.add(nueva_prueba)
        session.commit()
        session.refresh(nueva_prueba)
        return nueva_prueba

    @staticmethod
    def consultar_ensayos_obra(session: Session, id_obra: int) -> List[models.ControlCalidadPrueba]:
        return session.exec(
            select(models.ControlCalidadPrueba).where(models.ControlCalidadPrueba.id_obra == id_obra)
        ).all()

    @staticmethod
    def crear_reporte_diario(
        session: Session, reporte_in: models.ReporteDiarioSupervisionCreate
    ) -> models.ReporteDiarioSupervision:
        nuevo_reporte = models.ReporteDiarioSupervision.model_validate(reporte_in)
        session.add(nuevo_reporte)
        session.commit()
        session.refresh(nuevo_reporte)
        return nuevo_reporte

    @staticmethod
    def consultar_reportes_diarios(session: Session, id_obra: int) -> List[models.ReporteDiarioSupervision]:
        return session.exec(
            select(models.ReporteDiarioSupervision)
            .where(models.ReporteDiarioSupervision.id_obra == id_obra)
            .order_by(models.ReporteDiarioSupervision.fecha_reporte.desc())
        ).all()