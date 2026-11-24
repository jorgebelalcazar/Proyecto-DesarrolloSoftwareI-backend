"""Validaciones para los archivos que se reciben en la API."""

from rest_framework.exceptions import ValidationError

MAXIMO_PDF_BYTES = 10 * 1024 * 1024


def validar_pdf(archivo):
    """Verifica extensión, tamaño y firma PDF sin cambiar la posición del archivo."""
    if not archivo.name.lower().endswith(".pdf"):
        raise ValidationError({"archivo": "El archivo debe tener extensión .pdf."})
    if archivo.size > MAXIMO_PDF_BYTES:
        raise ValidationError({"archivo": "El tamaño máximo permitido es 10 MB."})

    posicion = archivo.tell()
    firma = archivo.read(5)
    archivo.seek(posicion)
    if firma != b"%PDF-":
        raise ValidationError({"archivo": "El contenido no tiene una firma PDF válida."})
    return archivo
