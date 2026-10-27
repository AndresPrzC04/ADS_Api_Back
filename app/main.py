from fastapi import FastAPI
from app.core.database import init_db

# Importación de los 4 módulos de modelos para que SQLModel registre las tablas
from app.modules.usuarios_accesos import models as usuarios_models
from app.modules.obras_contratos import models as obras_models
from app.modules.estimaciones import models as estimaciones_models
from app.modules.bitacora_expediente import models as bitacora_models

# Importación de routers
from app.modules.usuarios_accesos.router import router as usuarios_router
from app.modules.obras_contratos.router import router as obras_router
from app.modules.estimaciones.router import router as estimaciones_router
from app.modules.bitacora_expediente.router import router as bitacora_router

# Crea todas las tablas en la base de datos
init_db()

app = FastAPI(
    title="API - Sistema Administrador de Obras Públicas (SQLModel)",
    description="Backend unificado con SQLModel: Usuarios, Obras, Estimaciones, Bitácora Inmutable y Expediente.",
    version="1.0.0"
)

app.include_router(usuarios_router, prefix="/api/v1")
app.include_router(obras_router, prefix="/api/v1")
app.include_router(estimaciones_router, prefix="/api/v1")
app.include_router(bitacora_router, prefix="/api/v1")


@app.get("/", tags=["Healthcheck"])
def health_check():
    return {
        "estatus": "activo",
        "orm": "SQLModel",
        "modulos": [
            "01_05_usuarios_accesos",
            "02_obras_contratos",
            "03_estimaciones",
            "04_bitacora_expediente"
        ]
    }