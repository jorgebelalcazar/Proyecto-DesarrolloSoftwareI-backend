"""
Conexión con Supabase Storage para los PDF de los artículos (HU-16.1 y HU-19.1).

Los PDF se guardan en un bucket PRIVADO: nadie puede abrirlos con una URL
pública. Django se conecta con la llave "service_role", que tiene permisos
totales sobre el proyecto de Supabase; por eso:
  - solo existe en el .env del servidor, nunca en el repositorio ni en el front-end;
  - el front-end nunca habla con Supabase: le envía el PDF a Django, Django lo
    valida y Django lo sube.

Variables del .env (ver .env.example):
  SUPABASE_URL                 https://<proyecto>.supabase.co
  SUPABASE_SERVICE_ROLE_KEY    Project Settings > API Keys > service_role
  SUPABASE_STORAGE_BUCKET      nombre del bucket privado (por defecto "articulos")
"""

from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

# Vigencia de los enlaces firmados para ver un PDF (HU-19): 15 minutos.
VIGENCIA_URL_FIRMADA_SEGUNDOS = 15 * 60


def _bucket():
    """
    Devuelve el bucket de los artículos, listo para subir o borrar archivos.

    El SDK se importa aquí y no al inicio del archivo: así Django arranca
    rápido y las pruebas no necesitan conexión con Supabase.
    """
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise ImproperlyConfigured("Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en el .env.")
    if not settings.SUPABASE_STORAGE_BUCKET:
        raise ImproperlyConfigured("Falta SUPABASE_STORAGE_BUCKET en el .env.")

    from supabase import create_client

    cliente = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    return cliente.storage.from_(settings.SUPABASE_STORAGE_BUCKET)


def subir_pdf_articulo(articulo_id, archivo):
    """
    Sube el PDF al bucket y devuelve su ruta dentro de él.

    La ruta es "articulos/<id del artículo>/<uuid>.pdf". El nombre es un UUID
    aleatorio y no el nombre original del archivo: así dos archivos nunca se
    pisan, y un nombre malicioso (por ejemplo "../../otro.pdf") no puede
    cambiar la carpeta de destino.

    "upsert": "false" hace que Supabase rechace la subida si la ruta ya
    existe, en lugar de reemplazar un archivo.
    """
    ruta = f"articulos/{articulo_id}/{uuid4()}.pdf"
    archivo.seek(0)
    _bucket().upload(
        path=ruta,
        file=archivo.read(),
        file_options={"content-type": "application/pdf", "upsert": "false"},
    )
    return ruta


def eliminar_pdf_articulo(ruta):
    """
    Borra un archivo del bucket.

    Se usa cuando el PDF ya subió pero no se pudo registrar su versión en la
    base de datos: así no quedan archivos huérfanos ocupando espacio.
    """
    _bucket().remove([ruta])


def crear_url_firmada_pdf(ruta):
    """
    Genera un enlace temporal para abrir un PDF del bucket privado (HU-19.1).

    El enlace lleva un token firmado por Supabase y deja de funcionar a los
    15 minutos (VIGENCIA_URL_FIRMADA_SEGUNDOS). Así, aunque alguien lo copie
    y lo comparta, no sirve para siempre; para verlo otra vez, el usuario
    vuelve a abrir el detalle del artículo y recibe un enlace nuevo.
    """
    respuesta = _bucket().create_signed_url(ruta, VIGENCIA_URL_FIRMADA_SEGUNDOS)
    return respuesta["signedURL"]