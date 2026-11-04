from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.database import init_db
import app.models_base  # noqa: F401 - Registra las 29 tablas en SQLModel.metadata

# Importación de routers por módulo
from app.modules.usuario_accesos.router import router as usuarios_router
from app.modules.obras_contratos.router import router as obras_router
from app.modules.estimaciones.router import router as estimaciones_router
from app.modules.bitacora_expediente.router import router as bitacora_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="API - Sistema Administrador de Obras Públicas (SQLModel 3NF)",
    description=(
        "Backend unificado en 3NF con SQLModel: Gestión de Usuarios y Relevos, "
        "Obras y Contratos, Estimaciones y Generadores, Bitácora Electrónica Inmutable y Control de Calidad."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(usuarios_router, prefix="/api/v1")
app.include_router(obras_router, prefix="/api/v1")
app.include_router(estimaciones_router, prefix="/api/v1")
app.include_router(bitacora_router, prefix="/api/v1")


@app.get("/", tags=["Healthcheck"])
def health_check():
    return {
        "estatus": "activo",
        "orm": "SQLModel (3NF - 29 Tablas)",
        "modulos": [
            "usuarios_accesos",
            "obras_contratos",
            "estimaciones",
            "bitacora_expediente"
        ]
    }
