from datetime import date
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import String, Integer, Boolean, Date, Numeric, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class EmpresaContratista(Base):
    __tablename__ = "empresas_contratistas"

    id_empresa_contratista: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    razon_social: Mapped[str] = mapped_column(String(250), nullable=False)
    rfc: Mapped[str] = mapped_column(String(13), unique=True, nullable=False)
    domicilio_fiscal: Mapped[Optional[str]] = mapped_column(String(300))
    representante_legal: Mapped[str] = mapped_column(String(200), nullable=False)
    telefono: Mapped[Optional[str]] = mapped_column(String(20))
    correo: Mapped[str] = mapped_column(String(150), nullable=False)
    fecha_registro: Mapped[date] = mapped_column(Date, default=func.current_date())
    estado: Mapped[bool] = mapped_column(Boolean, default=True)

    contratos: Mapped[List["Contrato"]] = relationship(back_populates="empresa")


class Obra(Base):
    __tablename__ = "obras"

    id_obra: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    num_contrato: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(300), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[str] = mapped_column(String(50), default="ACTIVA")

    contratos: Mapped[List["Contrato"]] = relationship(back_populates="obra", cascade="all, delete-orphan")
    avances_fisicos: Mapped[List["AvanceFisico"]] = relationship(back_populates="obra", cascade="all, delete-orphan")
    insumos: Mapped[List["Insumo"]] = relationship(back_populates="obra", cascade="all, delete-orphan")
    conceptos: Mapped[List["ConceptoCatalogo"]] = relationship(back_populates="obra", cascade="all, delete-orphan")
    programa_ejecucion: Mapped[List["ProgramaEjecucion"]] = relationship(back_populates="obra", cascade="all, delete-orphan")


class Contrato(Base):
    __tablename__ = "contratos"

    id_contrato: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_obra: Mapped[int] = mapped_column(ForeignKey("obras.id_obra"), nullable=False)
    id_empresa_contratista: Mapped[int] = mapped_column(
        ForeignKey("empresas_contratistas.id_empresa_contratista"), nullable=False
    )
    monto_contrato: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    archivo_contrato: Mapped[str] = mapped_column(String(500), nullable=False)
    estado: Mapped[str] = mapped_column(String(50), default="BORRADOR")  # BORRADOR, VIGENTE, CERRADO

    obra: Mapped["Obra"] = relationship(back_populates="contratos")
    empresa: Mapped["EmpresaContratista"] = relationship(back_populates="contratos")
    polizas: Mapped[List["Poliza"]] = relationship(back_populates="contrato", cascade="all, delete-orphan")


class Poliza(Base):
    __tablename__ = "polizas"

    id_poliza: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_contrato: Mapped[int] = mapped_column(ForeignKey("contratos.id_contrato"), nullable=False)
    tipo_poliza: Mapped[str] = mapped_column(String(100), nullable=False)  # ANTICIPO, CUMPLIMIENTO, VICIOS_OCULTOS
    fecha_vencimiento: Mapped[date] = mapped_column(Date, nullable=False)
    archivo_poliza: Mapped[str] = mapped_column(String(500), nullable=False)

    contrato: Mapped["Contrato"] = relationship(back_populates="polizas")


class AvanceFisico(Base):
    __tablename__ = "avances_fisicos"

    id_avance: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_obra: Mapped[int] = mapped_column(ForeignKey("obras.id_obra"), nullable=False)
    fecha_corte: Mapped[date] = mapped_column(Date, nullable=False)
    porcentaje_fisico: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

    obra: Mapped["Obra"] = relationship(back_populates="avances_fisicos")


class Insumo(Base):
    __tablename__ = "insumos"

    id_insumo: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_obra: Mapped[int] = mapped_column(ForeignKey("obras.id_obra"), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(250), nullable=False)
    tipo_insumo: Mapped[str] = mapped_column(String(100), nullable=False)  # MATERIAL, MANO_OBRA, MAQUINARIA
    unidad: Mapped[str] = mapped_column(String(30), nullable=False)
    cantidad_insumo: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    costo_base: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    obra: Mapped["Obra"] = relationship(back_populates="insumos")
    conceptos_elementos: Mapped[List["ConceptoElemento"]] = relationship(back_populates="insumo")


class ConceptoCatalogo(Base):
    __tablename__ = "conceptos_catalogo"

    id_concepto: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_obra: Mapped[int] = mapped_column(ForeignKey("obras.id_obra"), nullable=False)
    clave_concepto: Mapped[str] = mapped_column(String(50), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    precio_bloqueado: Mapped[bool] = mapped_column(Boolean, default=False)

    obra: Mapped["Obra"] = relationship(back_populates="conceptos")
    elementos: Mapped[List["ConceptoElemento"]] = relationship(
        back_populates="concepto", cascade="all, delete-orphan"
    )
    actividades_programa: Mapped[List["ProgramaEjecucion"]] = relationship(
        back_populates="concepto", cascade="all, delete-orphan"
    )


class ConceptoElemento(Base):
    __tablename__ = "concepto_elementos"

    id_concepto_insumos: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_concepto: Mapped[int] = mapped_column(ForeignKey("conceptos_catalogo.id_concepto"), nullable=False)
    id_insumo: Mapped[int] = mapped_column(ForeignKey("insumos.id_insumo"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(100), nullable=False)
    unidad: Mapped[str] = mapped_column(String(30), nullable=False)
    cantidad: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    costo_base: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    concepto: Mapped["ConceptoCatalogo"] = relationship(back_populates="elementos")
    insumo: Mapped["Insumo"] = relationship(back_populates="conceptos_elementos")


class ProgramaEjecucion(Base):
    __tablename__ = "programa_ejecucion"

    id_actividad: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_obra: Mapped[int] = mapped_column(ForeignKey("obras.id_obra"), nullable=False)
    id_concepto: Mapped[int] = mapped_column(ForeignKey("conceptos_catalogo.id_concepto"), nullable=False)
    fecha_inicio_prog: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin_prog: Mapped[date] = mapped_column(Date, nullable=False)
    cant_programada: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)

    obra: Mapped["Obra"] = relationship(back_populates="programa_ejecucion")
    concepto: Mapped["ConceptoCatalogo"] = relationship(back_populates="actividades_programa")
