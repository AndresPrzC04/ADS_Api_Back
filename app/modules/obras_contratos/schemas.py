from datetime import date
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, EmailStr, ConfigDict, Field


# ==========================================
# 1. EMPRESA CONTRATISTA
# ==========================================
class EmpresaContratistaBase(BaseModel):
    razon_social: str = Field(..., max_length=250)
    rfc: str = Field(..., min_length=12, max_length=13)
    domicilio_fiscal: Optional[str] = Field(None, max_length=300)
    representante_legal: str = Field(..., max_length=200)
    telefono: Optional[str] = Field(None, max_length=20)
    correo: EmailStr


class EmpresaContratistaCreate(EmpresaContratistaBase):
    pass


class EmpresaContratistaUpdate(BaseModel):
    razon_social: Optional[str] = Field(None, max_length=250)
    domicilio_fiscal: Optional[str] = Field(None, max_length=300)
    representante_legal: Optional[str] = Field(None, max_length=200)
    telefono: Optional[str] = Field(None, max_length=20)
    correo: Optional[EmailStr] = None
    estado: Optional[bool] = None


class EmpresaContratistaPublic(EmpresaContratistaBase):
    id_empresa_contratista: int
    fecha_registro: date
    estado: bool

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 2. OBRA
# ==========================================
class ObraBase(BaseModel):
    num_contrato: str = Field(..., max_length=100)
    nombre: str = Field(..., max_length=300)
    descripcion: Optional[str] = None
    fecha_inicio: date
    fecha_fin: date


class ObraCreate(ObraBase):
    pass


class ObraUpdate(BaseModel):
    nombre: Optional[str] = Field(None, max_length=300)
    descripcion: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    estado: Optional[str] = None


class ObraPublic(ObraBase):
    id_obra: int
    estado: str

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 3. CONTRATO
# ==========================================
class ContratoBase(BaseModel):
    id_obra: int
    id_empresa_contratista: int
    monto_contrato: Decimal = Field(..., gt=0)
    archivo_contrato: str = Field(..., max_length=500)


class ContratoCreate(ContratoBase):
    pass


class ContratoUpdate(BaseModel):
    monto_contrato: Optional[Decimal] = Field(None, gt=0)
    archivo_contrato: Optional[str] = Field(None, max_length=500)
    estado: Optional[str] = None


class ContratoPublic(ContratoBase):
    id_contrato: int
    estado: str

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 4. PÓLIZA
# ==========================================
class PolizaBase(BaseModel):
    id_contrato: int
    tipo_poliza: str = Field(..., max_length=100, examples=["ANTICIPO", "CUMPLIMIENTO", "VICIOS_OCULTOS"])
    fecha_vencimiento: date
    archivo_poliza: str = Field(..., max_length=500)


class PolizaCreate(PolizaBase):
    pass


class PolizaUpdate(BaseModel):
    tipo_poliza: Optional[str] = Field(None, max_length=100)
    fecha_vencimiento: Optional[date] = None
    archivo_poliza: Optional[str] = Field(None, max_length=500)


class PolizaPublic(PolizaBase):
    id_poliza: int

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 5. AVANCE FÍSICO
# ==========================================
class AvanceFisicoBase(BaseModel):
    id_obra: int
    fecha_corte: date
    porcentaje_fisico: Decimal = Field(..., ge=0, le=100)


class AvanceFisicoCreate(AvanceFisicoBase):
    pass


class AvanceFisicoUpdate(BaseModel):
    fecha_corte: Optional[date] = None
    porcentaje_fisico: Optional[Decimal] = Field(None, ge=0, le=100)


class AvanceFisicoPublic(AvanceFisicoBase):
    id_avance: int

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 6. INSUMO (CATÁLOGO DE MATERIALES DE OBRA)
# ==========================================
class InsumoBase(BaseModel):
    id_obra: int
    descripcion: str = Field(..., max_length=250)
    tipo_insumo: str = Field(..., max_length=100, examples=["MATERIAL", "MANO_OBRA", "MAQUINARIA"])
    unidad: str = Field(..., max_length=30)
    cantidad_insumo: Decimal = Field(..., gt=0)
    costo_base: Decimal = Field(..., ge=0)


class InsumoCreate(InsumoBase):
    pass


class InsumoUpdate(BaseModel):
    descripcion: Optional[str] = Field(None, max_length=250)
    tipo_insumo: Optional[str] = Field(None, max_length=100)
    unidad: Optional[str] = Field(None, max_length=30)
    cantidad_insumo: Optional[Decimal] = Field(None, gt=0)
    costo_base: Optional[Decimal] = Field(None, ge=0)


class InsumoPublic(InsumoBase):
    id_insumo: int

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 7. CONCEPTO CATÁLOGO (PRESUPUESTO)
# ==========================================
class ConceptoCatalogoBase(BaseModel):
    id_obra: int
    clave_concepto: str = Field(..., max_length=50)
    descripcion: str
    precio_unitario: Decimal = Field(..., ge=0)


class ConceptoCatalogoCreate(ConceptoCatalogoBase):
    pass


class ConceptoCatalogoUpdate(BaseModel):
    clave_concepto: Optional[str] = Field(None, max_length=50)
    descripcion: Optional[str] = None
    precio_unitario: Optional[Decimal] = Field(None, ge=0)


class ConceptoCatalogoPublic(ConceptoCatalogoBase):
    id_concepto: int
    precio_bloqueado: bool

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 8. CONCEPTO ELEMENTO (DESGLOSE DE INSUMO EN CONCEPTO)
# ==========================================
class ConceptoElementoBase(BaseModel):
    id_concepto: int
    id_insumo: int
    tipo: str = Field(..., max_length=100)
    unidad: str = Field(..., max_length=30)
    cantidad: Decimal = Field(..., gt=0)
    costo_base: Decimal = Field(..., ge=0)


class ConceptoElementoCreate(ConceptoElementoBase):
    pass


class ConceptoElementoUpdate(BaseModel):
    cantidad: Optional[Decimal] = Field(None, gt=0)
    costo_base: Optional[Decimal] = Field(None, ge=0)


class ConceptoElementoPublic(ConceptoElementoBase):
    id_concepto_insumos: int

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 9. PROGRAMA DE EJECUCIÓN (CALENDARIO / GANTT)
# ==========================================
class ProgramaEjecucionBase(BaseModel):
    id_obra: int
    id_concepto: int
    fecha_inicio_prog: date
    fecha_fin_prog: date
    cant_programada: Decimal = Field(..., gt=0)


class ProgramaEjecucionCreate(ProgramaEjecucionBase):
    pass


class ProgramaEjecucionUpdate(BaseModel):
    fecha_inicio_prog: Optional[date] = None
    fecha_fin_prog: Optional[date] = None
    cant_programada: Optional[Decimal] = Field(None, gt=0)


class ProgramaEjecucionPublic(ProgramaEjecucionBase):
    id_actividad: int

    model_config = ConfigDict(from_attributes=True)