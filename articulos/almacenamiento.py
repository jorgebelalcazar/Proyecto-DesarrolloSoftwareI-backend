"""Conexión con el bucket privado de Supabase Storage."""

from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _cliente_supabase():
    """Crea el cliente con credenciales que solo existen en el servidor."""
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise ImproperlyConfigured("Falta configurar la conexión con Supabase.")
    if not settings.SUPABASE_STORAGE_BUCKET:
        raise ImproperlyConfigured("Falta configurar el bucket de Supabase Storage.")

    from supabase import create_client

    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def subir_pdf_articulo(articulo_id, archivo):
    """Sube el binario y devuelve su ruta privada dentro del bucket."""
    cliente = _cliente_supabase()
    ruta = f"articulos/{articulo_id}/{uuid4()}.pdf"
    archivo.seek(0)
    cliente.storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
        path=ruta,
        file=archivo.read(),
        file_options={"content-type": "application/pdf", "upsert": "false"},
    )
    return ruta


def eliminar_pdf_articulo(ruta):
    """Quita del bucket un archivo si no se pudo registrar en la base de datos."""
    cliente = _cliente_supabase()
    cliente.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove([ruta])
