import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
import bcrypt
import jwt
from fastapi import HTTPException, status

SECRET_KEY = os.getenv("SECRET_KEY", "clave_secreta_super_segura_obras_publicas_2026")
ALGORITHM = "HS256"
# RNF-SEG-05: Invalida la sesión tras 20 minutos de inactividad
ACCESS_TOKEN_EXPIRE_MINUTES = 20

EXTENSIONES_PROHIBIDAS = {".exe", ".js", ".bat", ".cmd", ".sh", ".ps1", ".php", ".py", ".dll", ".msi"}


def get_password_hash(plain_text: str) -> str:
    """Encripta contraseñas o firmas electrónicas usando bcrypt (RNF-SEG-01)."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain_text.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_text: str, hashed_text: str) -> bool:
    """Verifica una contraseña o firma electrónica en texto plano contra su hash."""
    if not hashed_text or not plain_text:
        return False
    return bcrypt.checkpw(plain_text.encode("utf-8"), hashed_text.encode("utf-8"))


def validar_firma_electronica_y_generar_sello(
    firma_plana: str,
    firma_hash_usuario: Optional[str],
    id_usuario: int,
    referencia: str
) -> str:
    """
    RNF-SEG-01 y RNF-SEG-04: Verifica la firma electrónica del usuario contra su hash en BD
    y genera un sello digital inmutable SHA-256 para estampar en bitácora o estimaciones.
    """
    if not firma_hash_usuario:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Su usuario no tiene configurada una firma electrónica activa."
        )
    if not verify_password(firma_plana, firma_hash_usuario):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La firma electrónica proporcionada es inválida."
        )
    marca_tiempo = datetime.now(timezone.utc).isoformat()
    cadena_original = f"USR:{id_usuario}|REF:{referencia}|TS:{marca_tiempo}"
    digest = hashlib.sha256(cadena_original.encode("utf-8")).hexdigest().upper()
    return f"SELLO-SHA256-{digest[:40]}"


def validar_formato_y_tamano_archivo(
    nombre_o_ruta: str,
    extensiones_validas: Tuple[str, ...],
    tamano_bytes: Optional[int] = None,
    max_mb: int = 10
) -> None:
    """
    RNF-REN-01, RNF-USA-05 y RN-SUPT-04.2: Rechaza ejecutables o scripts (.exe, .js, .bat)
    y verifica que el archivo pertenezca a las extensiones permitidas con máximo 10 MB.
    """
    if not nombre_o_ruta:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe especificar una ruta o nombre de archivo válido."
        )
    ruta_limpia = nombre_o_ruta.strip().lower().split("?")[0]
    _, ext = os.path.splitext(ruta_limpia)

    if ext in EXTENSIONES_PROHIBIDAS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Archivo rechazado por seguridad. Los scripts o ejecutables ({ext}) están estrictamente prohibidos."
        )

    ext_permitidas_norm = tuple(e.lower() for e in extensiones_validas)
    if ext not in ext_permitidas_norm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato '{ext}' no permitido. Formatos aceptados: {ext_permitidas_norm}"
        )

    limite_bytes = max_mb * 1024 * 1024
    if tamano_bytes is not None and tamano_bytes > limite_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El archivo excede el tamaño máximo permitido de {max_mb} MB."
        )


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión ha expirado por inactividad (20 minutos). Inicie sesión nuevamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        )
