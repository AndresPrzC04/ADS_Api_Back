from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import CheckConstraint, Column, Numeric, Text, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# =============================================================================
# BLOQUE 1: CATÁLOGOS MAESTROS INSTITUCIONALES (32 Tablas en 3NF Estricta)
# =============================================================================

# 1. Catálogo de Roles Únicos del Sistema
class RolUsuario(SQLModel, table=True):
    __tablename__ = "rol_usuario"

    id_rol_usuario: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    nombre: str = Field(max_length=50, unique=True, index=True)
    descripcion: Optional[str] = Field(default=None, max_length=255)
    activo: bool = Field(default=True)

    usuarios: List["Usuarios"] = Relationship(back_populates="rol")


# 2. Catálogo Maestro de Estatus por Ámbito
class CatEstatus(SQLModel, table=True):
    __tablename__ = "cat_estatus"
    __table_args__ = (
        UniqueConstraint("ambito", "clave", name="uq_estatus_ambito_clave"),
    )

    id_estatus: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    ambito: str = Field(max_length=30, index=True)
    clave: str = Field(max_length=50, index=True)
    nombre: str = Field(max_length=100)
    activo: bool = Field(default=True)


# 3. Catálogo de Unidades de Medida
class CatUnidadesMedida(SQLModel, table=True):
    __tablename__ = "cat_unidades_medida"

    id_unidad: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    clave: str = Field(max_length=20, unique=True, index=True)
    nombre: str = Field(max_length=100)
    activo: bool = Field(default=True)


# 4. Catálogo de Partidas Presupuestales (3NF)
class CatPartidas(SQLModel, table=True):
    __tablename__ = "cat_partidas"

    id_partida: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    nombre: str = Field(max_length=120, unique=True, index=True)
    activo: bool = Field(default=True)

    subpartidas: List["CatSubpartidas"] = Relationship(back_populates="partida")


# 5. Catálogo de Subpartidas Presupuestales (3NF)
class CatSubpartidas(SQLModel, table=True):
    __tablename__ = "cat_subpartidas"
    __table_args__ = (
        UniqueConstraint("id_partida", "nombre", name="uq_subpartida_por_partida"),
    )

    id_subpartida: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    id_partida: int = Field(foreign_key="cat_partidas.id_partida", index=True)
    nombre: str = Field(max_length=120, index=True)
    activo: bool = Field(default=True)

    partida: Optional[CatPartidas] = Relationship(back_populates="subpartidas")


# 6. Catálogo de Tipos de Concepto de Obra
class CatTipoConcepto(SQLModel, table=True):
    __tablename__ = "cat_tipo_concepto"

    id_tipo_concepto: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    clave: str = Field(max_length=30, unique=True, index=True)
    nombre: str = Field(max_length=100)
    requiere_apu: bool = Field(default=False)
    activo: bool = Field(default=True)


# 7. Catálogo Maestro General de Conceptos de Obra (Libro / Tabulador 3NF)
class CatConceptosMaestro(SQLModel, table=True):
    __tablename__ = "cat_conceptos_maestro"
    __table_args__ = (
        CheckConstraint(
            "precio_referencia IS NULL OR precio_referencia > 0",
            name="chk_precio_ref_positivo"
        ),
    )

    id_concepto_maestro: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    id_subpartida: int = Field(foreign_key="cat_subpartidas.id_subpartida", index=True)
    id_unidad: int = Field(foreign_key="cat_unidades_medida.id_unidad")
    clave_concepto: str = Field(max_length=100, unique=True, index=True)
    descripcion: str = Field(sa_column=Column(Text, nullable=False))
    precio_referencia: Optional[Decimal] = Field(
        default=None, sa_column=Column(Numeric(15, 2), nullable=True)
    )
    activo: bool = Field(default=True)

    subpartida_cat: Optional[CatSubpartidas] = Relationship()
    unidad: Optional[CatUnidadesMedida] = Relationship()
    obras_conceptos: List["ObraConceptos"] = Relationship(back_populates="concepto_maestro")


# 8. Catálogo de Tipos de Estimación
class CatTipoEstimacion(SQLModel, table=True):
    __tablename__ = "cat_tipo_estimacion"

    id_tipo_estimacion: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    clave: str = Field(max_length=40, unique=True, index=True)
    nombre: str = Field(max_length=100)
    descripcion: Optional[str] = Field(default=None, sa_column=Column(Text))
    activo: bool = Field(default=True)


# 9. Catálogo de Tipos de Póliza de Fianza
class CatTipoPoliza(SQLModel, table=True):
    __tablename__ = "cat_tipo_poliza"

    id_tipo_poliza: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    clave: str = Field(max_length=50, unique=True, index=True)
    nombre: str = Field(max_length=100)
    activo: bool = Field(default=True)


# 10. Catálogo de Tipos de Nota de Bitácora
class CatTipoNotaBitacora(SQLModel, table=True):
    __tablename__ = "cat_tipo_nota_bitacora"

    id_tipo_nota: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    clave: str = Field(max_length=50, unique=True, index=True)
    nombre: str = Field(max_length=120)
    id_rol_exclusivo: Optional[int] = Field(default=None, foreign_key="rol_usuario.id_rol_usuario")
    min_imagenes: int = Field(default=0)
    activo: bool = Field(default=True)

    rol_exclusivo: Optional[RolUsuario] = Relationship()


# 11. Catálogo de Tipos de Ensayo de Laboratorio
class CatTipoEnsayo(SQLModel, table=True):
    __tablename__ = "cat_tipo_ensayo"

    id_tipo_ensayo: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    clave: str = Field(max_length=40, unique=True, index=True)
    nombre: str = Field(max_length=150)
    norma_referencia: Optional[str] = Field(default=None, max_length=100)
    activo: bool = Field(default=True)


# 12. Catálogo de Tipos de Acción de Auditoría
class TipoAccion(SQLModel, table=True):
    __tablename__ = "tipo_accion"

    id_accion: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    tipo_accion: str = Field(max_length=100)
    accion_ejecutada: str = Field(max_length=255, unique=True, index=True)
    descripcion: Optional[str] = Field(default=None, sa_column=Column(Text))
    activo: bool = Field(default=True)


# 13. Padrón de Empresas Contratistas
class Contratistas(SQLModel, table=True):
    __tablename__ = "contratistas"

    id_contratista: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    rfc: str = Field(max_length=13, unique=True, index=True)
    razon_social: str = Field(max_length=255)
    activo: bool = Field(default=True)

    contratos: List["Contratos"] = Relationship(back_populates="contratista")
    correos_autorizados: List["CatCorreosAutorizados"] = Relationship(back_populates="contratista")


# 14. Diccionario de Correos y Dominios Autorizados
class CatCorreosAutorizados(SQLModel, table=True):
    __tablename__ = "cat_correos_autorizados"
    __table_args__ = (
        CheckConstraint("tipo_registro IN ('DOMINIO', 'CORREO')", name="chk_tipo_registro_correo"),
    )

    id_correo_autorizado: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    id_contratista: Optional[int] = Field(default=None, foreign_key="contratistas.id_contratista", index=True)
    tipo_registro: str = Field(max_length=20)
    valor: str = Field(max_length=150, unique=True, index=True)
    activo: bool = Field(default=True)

    contratista: Optional[Contratistas] = Relationship(back_populates="correos_autorizados")


# =============================================================================
# BLOQUE 2: TABLAS OPERATIVAS NORMALIZADAS EN 3NF ESTRICTA
# =============================================================================

# 15. Usuarios
class Usuarios(SQLModel, table=True):
    __tablename__ = "usuarios"

    id_usuario: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    id_rol_usuario: int = Field(foreign_key="rol_usuario.id_rol_usuario")
    nombre_completo: str = Field(max_length=255)
    correo: str = Field(max_length=150, unique=True, index=True)
    password_hash: str = Field(max_length=255)
    firma_electronica: Optional[str] = Field(default=None, max_length=255)
    activo: bool = Field(default=True)

    rol: Optional[RolUsuario] = Relationship(back_populates="usuarios")
    asignaciones: List["ObrasAsignaciones"] = Relationship(back_populates="usuario")


# 16. Obras Públicas
class Obras(SQLModel, table=True):
    __tablename__ = "obras"
    __table_args__ = (
        CheckConstraint("presupuesto_total > 0", name="chk_presupuesto_obra_positivo"),
        CheckConstraint("fecha_fin >= fecha_inicio", name="chk_fechas_obra"),
    )

    id_obra: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    id_estatus: int = Field(foreign_key="cat_estatus.id_estatus")
    nombre_obra: str = Field(max_length=255)
    presupuesto_total: Decimal = Field(sa_column=Column(Numeric(15, 2), nullable=False))
    fecha_inicio: date
    fecha_fin: date

    estatus: Optional[CatEstatus] = Relationship()
    asignaciones: List["ObrasAsignaciones"] = Relationship(back_populates="obra")
    contrato: Optional["Contratos"] = Relationship(back_populates="obra")
    conceptos: List["ObraConceptos"] = Relationship(back_populates="obra")
    estimaciones: List["Estimaciones"] = Relationship(back_populates="obra")
    avances_fisicos: List["AvancesFisicos"] = Relationship(back_populates="obra")
    bitacora_notas: List["BitacoraNotas"] = Relationship(back_populates="obra")
    reportes_diarios: List["ReporteDiarioSupervision"] = Relationship(back_populates="obra")


# 17. Asignaciones de Personal Operativo
class ObrasAsignaciones(SQLModel, table=True):
    __tablename__ = "obras_asignaciones"
    __table_args__ = (
        CheckConstraint(
            "fecha_fin_asignacion IS NULL OR fecha_fin_asignacion >= fecha_inicio_asignacion",
            name="chk_fechas_asignacion"
        ),
    )

    id_asignacion: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    id_usuario: int = Field(foreign_key="usuarios.id_usuario", index=True)
    id_obra: int = Field(foreign_key="obras.id_obra", index=True)
    fecha_inicio_asignacion: date
    fecha_fin_asignacion: Optional[date] = Field(default=None)

    usuario: Optional[Usuarios] = Relationship(back_populates="asignaciones")
    obra: Optional[Obras] = Relationship(back_populates="asignaciones")


# 18. Contratos Legales
class Contratos(SQLModel, table=True):
    __tablename__ = "contratos"
    __table_args__ = (
        CheckConstraint("monto_contrato > 0", name="chk_monto_contrato_positivo"),
        CheckConstraint(
            "monto_anticipo >= 0 AND monto_anticipo <= monto_contrato",
            name="chk_monto_anticipo_rango"
        ),
    )

    id_contrato: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    id_obra: int = Field(foreign_key="obras.id_obra", unique=True, index=True)
    id_contratista: int = Field(foreign_key="contratistas.id_contratista")
    id_estatus: int = Field(foreign_key="cat_estatus.id_estatus")
    numero_contrato: str = Field(max_length=100, unique=True, index=True)
    monto_contrato: Decimal = Field(sa_column=Column(Numeric(15, 2), nullable=False))
    monto_anticipo: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(15, 2), nullable=False)
    )
    archivo_contrato: Optional[str] = Field(default=None, max_length=255)

    obra: Optional[Obras] = Relationship(back_populates="contrato")
    contratista: Optional[Contratistas] = Relationship(back_populates="contratos")
    estatus: Optional[CatEstatus] = Relationship()
    polizas: List["Polizas"] = Relationship(back_populates="contrato")


# 19. Pólizas de Fianza
class Polizas(SQLModel, table=True):
    __tablename__ = "polizas"

    id_poliza: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    id_contrato: int = Field(foreign_key="contratos.id_contrato", index=True)
    id_tipo_poliza: int = Field(foreign_key="cat_tipo_poliza.id_tipo_poliza")
    numero_poliza: str = Field(max_length=100, unique=True, index=True)
    fecha_vencimiento: date
    archivo_poliza: str = Field(max_length=255)

    contrato: Optional[Contratos] = Relationship(back_populates="polizas")
    tipo_poliza: Optional[CatTipoPoliza] = Relationship()


# 20. Conceptos Asignados por Obra (3NF: Tabla asociativa Obras <-> Cat_Conceptos_Maestro)
class ObraConceptos(SQLModel, table=True):
    __tablename__ = "obra_conceptos"
    __table_args__ = (
        UniqueConstraint("id_obra", "id_concepto_maestro", name="uq_concepto_maestro_por_obra"),
        CheckConstraint("cantidad_presupuestada >= 0", name="chk_cant_presupuestada"),
        CheckConstraint("cantidad_adicional_autorizada >= 0", name="chk_cant_adicional"),
        CheckConstraint("precio_unitario > 0", name="chk_precio_unitario_positivo"),
    )

    id_obra_concepto: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    id_obra: int = Field(foreign_key="obras.id_obra", index=True)
    id_concepto_maestro: int = Field(foreign_key="cat_conceptos_maestro.id_concepto_maestro", index=True)
    id_tipo_concepto: int = Field(foreign_key="cat_tipo_concepto.id_tipo_concepto")
    cantidad_presupuestada: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(15, 2), nullable=False)
    )
    cantidad_adicional_autorizada: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(15, 2), nullable=False)
    )
    precio_unitario: Decimal = Field(sa_column=Column(Numeric(15, 2), nullable=False))
    dictamen_apu_url: Optional[str] = Field(default=None, max_length=255)
    autorizado_por_residente: bool = Field(default=True)

    obra: Optional[Obras] = Relationship(back_populates="conceptos")
    concepto_maestro: Optional[CatConceptosMaestro] = Relationship(back_populates="obras_conceptos")
    tipo_concepto: Optional[CatTipoConcepto] = Relationship()
    pruebas_calidad: List["ControlCalidadPruebas"] = Relationship(back_populates="obra_concepto")


# 21. Estimaciones de Obra
class Estimaciones(SQLModel, table=True):
    __tablename__ = "estimaciones"
    __table_args__ = (
        UniqueConstraint("id_obra", "numero_estimacion", name="uq_numero_estimacion_obra"),
        CheckConstraint("numero_estimacion > 0", name="chk_numero_estimacion_positivo"),
        CheckConstraint("version_subsanacion >= 1", name="chk_version_subsanacion_min"),
        CheckConstraint("periodo_fin >= periodo_inicio", name="chk_periodo_estimacion"),
        CheckConstraint("iva >= 0", name="chk_iva_no_negativo"),
        CheckConstraint("retencion_atraso >= 0", name="chk_retencion_atraso_no_negativa"),
        CheckConstraint("retencion_sfp >= 0", name="chk_retencion_sfp_no_negativa"),
    )

    id_estimacion: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    id_obra: int = Field(foreign_key="obras.id_obra", index=True)
    id_superintendente: int = Field(foreign_key="usuarios.id_usuario")
    id_tipo_estimacion: int = Field(foreign_key="cat_tipo_estimacion.id_tipo_estimacion")
    id_estatus: int = Field(foreign_key="cat_estatus.id_estatus")
    numero_estimacion: int
    version_subsanacion: int = Field(default=1)
    periodo_inicio: date
    periodo_fin: date
    fecha_presentacion: date = Field(default_factory=date.today)
    monto_bruto: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(15, 2), nullable=False)
    )
    monto_amortizacion: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(15, 2), nullable=False)
    )
    iva: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(15, 2), nullable=False)
    )
    retencion_atraso: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(15, 2), nullable=False)
    )
    retencion_sfp: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(15, 2), nullable=False)
    )
    monto_neto: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(15, 2), nullable=False)
    )

    obra: Optional[Obras] = Relationship(back_populates="estimaciones")
    tipo_estimacion: Optional[CatTipoEstimacion] = Relationship()
    estatus: Optional[CatEstatus] = Relationship()
    detalles: List["EstimacionDetalles"] = Relationship(back_populates="estimacion")
    revisiones: List["RevisionEstimaciones"] = Relationship(back_populates="estimacion")
    facturacion: Optional["FacturacionEstimacion"] = Relationship(back_populates="estimacion")
    pago: Optional["EstimacionesPagadas"] = Relationship(back_populates="estimacion")


# 22. Detalles por Concepto de Estimaciones (3NF)
class EstimacionDetalles(SQLModel, table=True):
    __tablename__ = "estimacion_detalles"
    __table_args__ = (
        UniqueConstraint("id_estimacion", "id_obra_concepto", name="uq_detalle_estimacion_concepto"),
        CheckConstraint("cantidad_estimada > 0", name="chk_cant_estimada_pos"),
    )

    id_estimacion_detalle: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    id_estimacion: int = Field(foreign_key="estimaciones.id_estimacion", index=True)
    id_obra_concepto: int = Field(foreign_key="obra_conceptos.id_obra_concepto", index=True)
    cantidad_estimada: Decimal = Field(sa_column=Column(Numeric(15, 2), nullable=False))

    estimacion: Optional[Estimaciones] = Relationship(back_populates="detalles")
    obra_concepto: Optional[ObraConceptos] = Relationship()


# 23. Revisión y Dictamen de Estimaciones
class RevisionEstimaciones(SQLModel, table=True):
    __tablename__ = "revision_estimaciones"
    __table_args__ = (
        UniqueConstraint("id_estimacion", "version_revisada", name="uq_revision_estimacion_version"),
        CheckConstraint("version_revisada >= 1", name="chk_version_revisada_rev"),
    )

    id_revision: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    id_estimacion: int = Field(foreign_key="estimaciones.id_estimacion", index=True)
    id_supervisor: int = Field(foreign_key="usuarios.id_usuario")
    id_estatus_revision: int = Field(foreign_key="cat_estatus.id_estatus")
    version_revisada: int = Field(default=1)
    fecha_recepcion: date = Field(default_factory=date.today)
    fecha_autorizacion: Optional[date] = Field(default=None)
    observaciones_rechazo: Optional[str] = Field(default=None, sa_column=Column(Text))
    monto_autorizado_neto: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(15, 2), nullable=False)
    )
    sello_firma_supervisor: Optional[str] = Field(default=None, max_length=255)

    estimacion: Optional[Estimaciones] = Relationship(back_populates="revisiones")
    estatus_revision: Optional[CatEstatus] = Relationship()


# 24. Documentos Fiscales CFDI
class FacturacionEstimacion(SQLModel, table=True):
    __tablename__ = "facturacion_estimacion"
    __table_args__ = (
        CheckConstraint("monto_factura > 0", name="chk_monto_factura_positivo"),
    )

    id_factura: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    id_estimacion: int = Field(foreign_key="estimaciones.id_estimacion", unique=True, index=True)
    folio_fiscal: str = Field(max_length=100, unique=True, index=True)
    monto_factura: Decimal = Field(sa_column=Column(Numeric(15, 2), nullable=False))
    ruta_pdf: str = Field(max_length=255)
    ruta_xml: str = Field(max_length=255)
    fecha_carga: datetime = Field(default_factory=utc_now)

    estimacion: Optional[Estimaciones] = Relationship(back_populates="facturacion")


# 25. Estimaciones Pagadas
class EstimacionesPagadas(SQLModel, table=True):
    __tablename__ = "estimaciones_pagadas"
    __table_args__ = (
        CheckConstraint("monto_pagado > 0", name="chk_monto_pagado_positivo"),
    )

    id_estimacion: int = Field(foreign_key="estimaciones.id_estimacion", primary_key=True)
    id_estatus_pago: int = Field(foreign_key="cat_estatus.id_estatus")
    folio_estimacion: str = Field(max_length=100, unique=True, index=True)
    monto_pagado: Decimal = Field(sa_column=Column(Numeric(15, 2), nullable=False))
    fecha_pago: date

    estimacion: Optional[Estimaciones] = Relationship(back_populates="pago")
    estatus_pago: Optional[CatEstatus] = Relationship()


# 26. Reporte Diario de Supervisión (3NF: id_estatus_reporte FK -> Cat_Estatus, incidentes en tabla hija)
class ReporteDiarioSupervision(SQLModel, table=True):
    __tablename__ = "reporte_diario_supervision"
    __table_args__ = (
        UniqueConstraint("id_obra", "fecha_reporte", name="uq_reporte_diario_obra_fecha"),
        CheckConstraint(
            "clima IS NULL OR clima IN ('SOLEADO', 'NUBLADO', 'LLUVIOSO', 'TORMENTA')",
            name="chk_clima_reporte"
        ),
        CheckConstraint(
            "horas_lluvia >= 0 AND horas_lluvia <= 24",
            name="chk_horas_lluvia"
        ),
        CheckConstraint("maquinaria_cantidad >= 0", name="chk_maquinaria_no_negativa"),
        CheckConstraint("equipo_cantidad >= 0", name="chk_equipo_no_negativo"),
        CheckConstraint("personal_cantidad >= 0", name="chk_personal_no_negativo"),
        CheckConstraint(
            "porcentaje_avance_reportado IS NULL OR (porcentaje_avance_reportado >= 0 AND porcentaje_avance_reportado <= 100)",
            name="chk_porcentaje_avance_rango"
        ),
    )

    id_reporte: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    id_obra: int = Field(foreign_key="obras.id_obra", index=True)
    id_supervisor: int = Field(foreign_key="usuarios.id_usuario")
    id_estatus_reporte: int = Field(foreign_key="cat_estatus.id_estatus", index=True)
    fecha_reporte: date
    actividades_realizadas: Optional[str] = Field(default=None, sa_column=Column(Text))
    clima: Optional[str] = Field(default=None, max_length=20)
    horas_lluvia: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(4, 2), nullable=False)
    )
    maquinaria_cantidad: int = Field(default=0)
    equipo_cantidad: int = Field(default=0)
    personal_cantidad: int = Field(default=0)
    porcentaje_avance_reportado: Optional[Decimal] = Field(
        default=None, sa_column=Column(Numeric(5, 2), nullable=True)
    )
    sello_digital: Optional[str] = Field(default=None, max_length=255)
    fecha_envio: Optional[datetime] = Field(default=None)
    fecha_firma: Optional[datetime] = Field(default=None)

    obra: Optional[Obras] = Relationship(back_populates="reportes_diarios")
    estatus_reporte_cat: Optional[CatEstatus] = Relationship()
    evidencias: List["EvidenciaAdjunta"] = Relationship(back_populates="reporte")
    incidentes: List["ReporteIncidentes"] = Relationship(back_populates="reporte")


# 27. Incidentes de Reporte Diario de Supervisión (3NF)
class ReporteIncidentes(SQLModel, table=True):
    __tablename__ = "reporte_incidentes"

    id_incidente: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    id_reporte: int = Field(foreign_key="reporte_diario_supervision.id_reporte", index=True)
    id_estatus_incidente: int = Field(foreign_key="cat_estatus.id_estatus", index=True)
    suceso: str = Field(sa_column=Column(Text, nullable=False))
    accion_solucion: Optional[str] = Field(default=None, sa_column=Column(Text))

    reporte: Optional[ReporteDiarioSupervision] = Relationship(back_populates="incidentes")
    estatus_incidente: Optional[CatEstatus] = Relationship()


# 28. Cortes Oficiales de Avance Físico y Financiero Real
class AvancesFisicos(SQLModel, table=True):
    __tablename__ = "avances_fisicos"
    __table_args__ = (
        CheckConstraint("porcentaje_financiero_real <= porcentaje_fisico", name="chk_candado_fisico_financiero"),
        CheckConstraint("porcentaje_fisico >= 0 AND porcentaje_fisico <= 100", name="chk_fisico_rango"),
        CheckConstraint("porcentaje_financiero_real >= 0 AND porcentaje_financiero_real <= 100", name="chk_fin_rango"),
    )

    id_avance: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    id_obra: int = Field(foreign_key="obras.id_obra", index=True)
    id_reporte: Optional[int] = Field(default=None, foreign_key="reporte_diario_supervision.id_reporte", index=True)
    fecha_corte: date
    porcentaje_fisico: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(5, 2), nullable=False)
    )
    porcentaje_financiero_real: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(5, 2), nullable=False)
    )

    obra: Optional[Obras] = Relationship(back_populates="avances_fisicos")


# 29. Bitácora Electrónica de Obra Inmutable
class BitacoraNotas(SQLModel, table=True):
    __tablename__ = "bitacora_notas"
    __table_args__ = (
        UniqueConstraint("id_obra", "consecutivo_nota", name="uq_consecutivo_bitacora_obra"),
        CheckConstraint("consecutivo_nota >= 1", name="chk_consecutivo_nota_min"),
    )

    id_nota: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    id_obra: int = Field(foreign_key="obras.id_obra", index=True)
    id_usuario: int = Field(foreign_key="usuarios.id_usuario")
    id_tipo_nota: int = Field(foreign_key="cat_tipo_nota_bitacora.id_tipo_nota")
    consecutivo_nota: int
    asunto: str = Field(max_length=255)
    descripcion: str = Field(sa_column=Column(Text, nullable=False))
    fecha_registro: datetime = Field(default_factory=utc_now)
    firmada: bool = Field(default=False)
    sello_digital: Optional[str] = Field(default=None, max_length=255)

    obra: Optional[Obras] = Relationship(back_populates="bitacora_notas")
    tipo_nota_cat: Optional[CatTipoNotaBitacora] = Relationship()
    evidencias: List["EvidenciaAdjunta"] = Relationship(back_populates="nota")


# 30. Evidencia Fotográfica Adjunta
class EvidenciaAdjunta(SQLModel, table=True):
    __tablename__ = "evidencia_adjunta"
    __table_args__ = (
        CheckConstraint(
            "(id_nota IS NOT NULL AND id_reporte IS NULL) OR (id_nota IS NULL AND id_reporte IS NOT NULL)",
            name="chk_evidencia_origen_unico"
        ),
    )

    id_evidencia: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    id_nota: Optional[int] = Field(default=None, foreign_key="bitacora_notas.id_nota", index=True)
    id_reporte: Optional[int] = Field(default=None, foreign_key="reporte_diario_supervision.id_reporte", index=True)
    ruta_archivo: str = Field(max_length=255)
    descripcion_pie_foto: Optional[str] = Field(default=None, max_length=255)
    fecha_carga: datetime = Field(default_factory=utc_now)

    nota: Optional[BitacoraNotas] = Relationship(back_populates="evidencias")
    reporte: Optional[ReporteDiarioSupervision] = Relationship(back_populates="evidencias")


# 31. Control de Calidad y Pruebas de Laboratorio
class ControlCalidadPruebas(SQLModel, table=True):
    __tablename__ = "control_calidad_pruebas"

    id_prueba: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    id_obra_concepto: int = Field(foreign_key="obra_conceptos.id_obra_concepto", index=True)
    id_tipo_ensayo: int = Field(foreign_key="cat_tipo_ensayo.id_tipo_ensayo")
    id_estatus_dictamen: int = Field(foreign_key="cat_estatus.id_estatus")
    fecha_muestreo: date
    valor_obtenido: str = Field(max_length=100)
    url_reporte_laboratorio: str = Field(max_length=255)

    obra_concepto: Optional[ObraConceptos] = Relationship(back_populates="pruebas_calidad")
    tipo_ensayo_cat: Optional[CatTipoEnsayo] = Relationship()
    estatus_dictamen: Optional[CatEstatus] = Relationship()


# 32. Registro Inmutable de Auditoría
class AuditoriaLogs(SQLModel, table=True):
    __tablename__ = "auditoria_logs"

    id_log: int = Field(default=None, primary_key=True)  # type: ignore[assignment]
    id_obra: Optional[int] = Field(default=None, foreign_key="obras.id_obra")
    id_usuario: int = Field(foreign_key="usuarios.id_usuario")
    id_accion: int = Field(foreign_key="tipo_accion.id_accion")
    ip_origen: Optional[str] = Field(default=None, max_length=45)
    fecha_inicio: datetime = Field(default_factory=utc_now)
    fecha_cierre: datetime = Field(default_factory=utc_now)
