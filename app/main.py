from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import init_db
import app.models_base  # noqa: F401 - Registra las 32 tablas en 3NF estricta en SQLModel.metadata

# Importación de routers por módulo
from app.modules.usuarios_accesos.router import router as usuarios_router
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
        "Backend unificado en 3NF con SQLModel (32 tablas en 3NF estricta): Gestión de Usuarios y Diccionario de Correos, "
        "Obras y Contratos, Estimaciones, Bitácora Inmutable y Reportes de Supervisión con Avance Físico."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(usuarios_router, prefix="/api/v1")
app.include_router(obras_router, prefix="/api/v1")
app.include_router(estimaciones_router, prefix="/api/v1")
app.include_router(bitacora_router, prefix="/api/v1")


@app.get("/", tags=["Healthcheck"])
def health_check():
    return {
        "estatus": "activo",
        "orm": "SQLModel (3NF - 32 Tablas - 3NF Estricta)",
        "modulos": [
            "usuarios_accesos",
            "obras_contratos",
            "estimaciones",
            "bitacora_expediente"
        ]
    }
