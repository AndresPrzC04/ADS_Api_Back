from datetime import date
from decimal import Decimal
from typing import List, Optional
from pydantic import EmailStr
from sqlalchemy import Column, Numeric, Text
from sqlmodel import SQLModel, Field, Relationship


# =====================================================================
# 1. EMPRESA CONTRATISTA
# =====================================================================
class EmpresaContratistaBase(SQLModel):
    razon_social: str = Field(max_length=250)
    rfc: str = Field(unique=True, index=True, min_length=12, max_length=13)
    domicilio_fiscal: Optional[str] = Field(default=None, max_length=300)
    representante_legal: str = Field(max_length=200)
    telefono: Optional[str] = Field(default=None, max_length=20)
    correo: EmailStr = Field(max_length=150)


class EmpresaContratista(EmpresaContratistaBase, table=True):
    __tablename__ = "empresas_contratistas"

    id_empresa_contratista: Optional[int] = Field(default=None, primary_key=True)
    fecha_registro: date = Field(default_factory=date.today)
    estado: bool = Field(default=True)

    contratos: List["Contrato"] = Relationship(back_populates="empresa")


class EmpresaContratistaCreate(EmpresaContratistaBase):
    pass


class EmpresaContratistaUpdate(SQLModel):
    razon_social: Optional[str] = Field(default=None, max_length=250)
    domicilio_fiscal: Optional[str] = Field(default=None, max_length=300)
    representante_legal: Optional[str] = Field(default=None, max_length=200)
    telefono: Optional[str] = Field(default=None, max_length=20)
    correo: Optional[EmailStr] = None
    estado: Optional[bool] = None


class EmpresaContratistaPublic(EmpresaContratistaBase):
    id_empresa_contratista: int
    fecha_registro: date
    estado: bool


# =====================================================================
# 2. OBRA
# =====================================================================
class ObraBase(SQLModel):
    num_contrato: str = Field(unique=True, index=True, max_length=100)
    nombre: str = Field(max_length=300)
    descripcion: Optional[str] = Field(default=None, sa_column=Column(Text))
    fecha_inicio: date
    fecha_fin: date


class Obra(ObraBase, table=True):
    __tablename__ = "obras"

    id_obra: Optional[int] = Field(default=None, primary_key=True)
    estado: str = Field(default="ACTIVA", max_length=50)

    contratos: List["Contrato"] = Relationship(back_populates="obra")
    avances_fisicos: List["AvanceFisico"] = Relationship(back_populates="obra")
    insumos: List["Insumo"] = Relationship(back_populates="obra")
    conceptos: List["ConceptoCatalogo"] = Relationship(back_populates="obra")
    programa_ejecucion: List["ProgramaEjecucion"] = Relationship(back_populates="obra")


class ObraCreate(ObraBase):
    pass


class ObraUpdate(SQLModel):
    nombre: Optional[str] = Field(default=None, max_length=300)
    descripcion: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    estado: Optional[str] = None


class ObraPublic(ObraBase):
    id_obra: int
    estado: str


# =====================================================================
# 3. CONTRATO
# =====================================================================
class ContratoBase(SQLModel):
    id_obra: int = Field(foreign_key="obras.id_obra")
    id_empresa_contratista: int = Field(foreign_key="empresas_contratistas.id_empresa_contratista")
    monto_contrato: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(16, 2), nullable=False)
    )
    archivo_contrato: str = Field(max_length=500)


class Contrato(ContratoBase, table=True):
    __tablename__ = "contratos"

    id_contrato: Optional[int] = Field(default=None, primary_key=True)
    estado: str = Field(default="BORRADOR", max_length=50)

    obra: Optional[Obra] = Relationship(back_populates="contratos")
    empresa: Optional[EmpresaContratista] = Relationship(back_populates="contratos")
    polizas: List["Poliza"] = Relationship(back_populates="contrato")


class ContratoCreate(ContratoBase):
    pass


class ContratoUpdate(SQLModel):
    monto_contrato: Optional[Decimal] = None
    archivo_contrato: Optional[str] = Field(default=None, max_length=500)
    estado: Optional[str] = None


class ContratoPublic(ContratoBase):
    id_contrato: int
    estado: str


# =====================================================================
# 4. PÓLIZA
# =====================================================================
class PolizaBase(SQLModel):
    id_contrato: int = Field(foreign_key="contratos.id_contrato")
    tipo_poliza: str = Field(max_length=100)
    fecha_vencimiento: date
    archivo_poliza: str = Field(max_length=500)


class Poliza(PolizaBase, table=True):
    __tablename__ = "polizas"

    id_poliza: Optional[int] = Field(default=None, primary_key=True)
    contrato: Optional[Contrato] = Relationship(back_populates="polizas")


class PolizaCreate(PolizaBase):
    pass


class PolizaUpdate(SQLModel):
    tipo_poliza: Optional[str] = Field(default=None, max_length=100)
    fecha_vencimiento: Optional[date] = None
    archivo_poliza: Optional[str] = Field(default=None, max_length=500)


class PolizaPublic(PolizaBase):
    id_poliza: int


# =====================================================================
# 5. AVANCE FÍSICO
# =====================================================================
class AvanceFisicoBase(SQLModel):
    id_obra: int = Field(foreign_key="obras.id_obra")
    fecha_corte: date
    porcentaje_fisico: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(5, 2), nullable=False)
    )


class AvanceFisico(AvanceFisicoBase, table=True):
    __tablename__ = "avances_fisicos"

    id_avance: Optional[int] = Field(default=None, primary_key=True)
    obra: Optional[Obra] = Relationship(back_populates="avances_fisicos")


class AvanceFisicoCreate(AvanceFisicoBase):
    pass


class AvanceFisicoUpdate(SQLModel):
    fecha_corte: Optional[date] = None
    porcentaje_fisico: Optional[Decimal] = None


class AvanceFisicoPublic(AvanceFisicoBase):
    id_avance: int


# =====================================================================
# 6. INSUMO (Catálogo Maestro de Obra)
# =====================================================================
class InsumoBase(SQLModel):
    id_obra: int = Field(foreign_key="obras.id_obra")
    descripcion: str = Field(max_length=250)
    tipo_insumo: str = Field(max_length=100)
    unidad: str = Field(max_length=30)
    cantidad_insumo: Decimal = Field(
        default=Decimal("0.0000"), sa_column=Column(Numeric(14, 4), nullable=False)
    )
    costo_base: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(14, 2), nullable=False)
    )


class Insumo(InsumoBase, table=True):
    __tablename__ = "insumos"

    id_insumo: Optional[int] = Field(default=None, primary_key=True)

    obra: Optional[Obra] = Relationship(back_populates="insumos")
    conceptos_elementos: List["ConceptoElemento"] = Relationship(back_populates="insumo")


class InsumoCreate(InsumoBase):
    pass


class InsumoUpdate(SQLModel):
    descripcion: Optional[str] = Field(default=None, max_length=250)
    tipo_insumo: Optional[str] = Field(default=None, max_length=100)
    unidad: Optional[str] = Field(default=None, max_length=30)
    cantidad_insumo: Optional[Decimal] = None
    costo_base: Optional[Decimal] = None


class InsumoPublic(InsumoBase):
    id_insumo: int


# =====================================================================
# 7. CONCEPTO CATÁLOGO (Presupuesto)
# =====================================================================
class ConceptoCatalogoBase(SQLModel):
    id_obra: int = Field(foreign_key="obras.id_obra")
    clave_concepto: str = Field(max_length=50)
    descripcion: str = Field(sa_column=Column(Text, nullable=False))
    precio_unitario: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(14, 2), nullable=False)
    )


class ConceptoCatalogo(ConceptoCatalogoBase, table=True):
    __tablename__ = "conceptos_catalogo"

    id_concepto: Optional[int] = Field(default=None, primary_key=True)
    precio_bloqueado: bool = Field(default=False)

    obra: Optional[Obra] = Relationship(back_populates="conceptos")
    elementos: List["ConceptoElemento"] = Relationship(back_populates="concepto")
    actividades_programa: List["ProgramaEjecucion"] = Relationship(back_populates="concepto")


class ConceptoCatalogoCreate(ConceptoCatalogoBase):
    pass


class ConceptoCatalogoUpdate(SQLModel):
    clave_concepto: Optional[str] = Field(default=None, max_length=50)
    descripcion: Optional[str] = None
    precio_unitario: Optional[Decimal] = None


class ConceptoCatalogoPublic(ConceptoCatalogoBase):
    id_concepto: int
    precio_bloqueado: bool


# =====================================================================
# 8. CONCEPTO ELEMENTO (Desglose Insumo en Concepto)
# =====================================================================
class ConceptoElementoBase(SQLModel):
    id_concepto: int = Field(foreign_key="conceptos_catalogo.id_concepto")
    id_insumo: int = Field(foreign_key="insumos.id_insumo")
    tipo: str = Field(max_length=100)
    unidad: str = Field(max_length=30)
    cantidad: Decimal = Field(
        default=Decimal("0.0000"), sa_column=Column(Numeric(14, 4), nullable=False)
    )
    costo_base: Decimal = Field(
        default=Decimal("0.00"), sa_column=Column(Numeric(14, 2), nullable=False)
    )


class ConceptoElemento(ConceptoElementoBase, table=True):
    __tablename__ = "concepto_elementos"

    id_concepto_insumos: Optional[int] = Field(default=None, primary_key=True)

    concepto: Optional[ConceptoCatalogo] = Relationship(back_populates="elementos")
    insumo: Optional[Insumo] = Relationship(back_populates="conceptos_elementos")


class ConceptoElementoCreate(ConceptoElementoBase):
    pass


class ConceptoElementoUpdate(SQLModel):
    cantidad: Optional[Decimal] = None
    costo_base: Optional[Decimal] = None


class ConceptoElementoPublic(ConceptoElementoBase):
    id_concepto_insumos: int


# =====================================================================
# 9. PROGRAMA DE EJECUCIÓN (Cronograma / Gantt)
# =====================================================================
class ProgramaEjecucionBase(SQLModel):
    id_obra: int = Field(foreign_key="obras.id_obra")
    id_concepto: int = Field(foreign_key="conceptos_catalogo.id_concepto")
    fecha_inicio_prog: date
    fecha_fin_prog: date
    cant_programada: Decimal = Field(
        default=Decimal("0.0000"), sa_column=Column(Numeric(14, 4), nullable=False)
    )


class ProgramaEjecucion(ProgramaEjecucionBase, table=True):
    __tablename__ = "programa_ejecucion"

    id_actividad: Optional[int] = Field(default=None, primary_key=True)

    obra: Optional[Obra] = Relationship(back_populates="programa_ejecucion")
    concepto: Optional[ConceptoCatalogo] = Relationship(back_populates="actividades_programa")


class ProgramaEjecucionCreate(ProgramaEjecucionBase):
    pass


class ProgramaEjecucionUpdate(SQLModel):
    fecha_inicio_prog: Optional[date] = None
    fecha_fin_prog: Optional[date] = None
    cant_programada: Optional[Decimal] = None


class ProgramaEjecucionPublic(ProgramaEjecucionBase):
    id_actividad: int