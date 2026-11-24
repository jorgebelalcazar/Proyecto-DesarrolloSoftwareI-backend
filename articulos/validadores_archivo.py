"""
Validación de los archivos PDF que recibe la API (HU-16.2).

Es la validación del SERVIDOR. El front-end también bloquea los archivos
inválidos antes de enviarlos (HU-16.4), pero esa validación se puede saltar
con Postman o con las herramientas del navegador: la que vale es esta
(HU-16, criterio 3: doble validación).
"""

from rest_framework import serializers

# 10 MB (HU-16, criterio 1). Se cuentan como 10 x 1024 x 1024 bytes.
MAX_BYTES_PDF = 10 * 1024 * 1024

# Todo archivo PDF empieza con estos 5 bytes, que lo identifican como PDF.
FIRMA_PDF = b"%PDF-"


def validar_pdf(archivo):
    """
    Revisa que el archivo sea un PDF de máximo 10 MB.

    Tres comprobaciones, de la más barata a la más costosa:
      1. La extensión es .pdf.
      2. El tamaño no supera 10 MB.
      3. Los primeros bytes son la firma "%PDF-". Detecta, por ejemplo, un
         .docx al que solo se le cambió el nombre a .pdf.

    Devuelve el mismo archivo, con la posición de lectura al inicio, para
    que luego se pueda subir completo.
    """
    if not archivo.name.lower().endswith(".pdf"):
        raise serializers.ValidationError("El archivo debe tener extensión .pdf.")

    if archivo.size > MAX_BYTES_PDF:
        megas = archivo.size / (1024 * 1024)
        raise serializers.ValidationError(
            f"El archivo pesa {megas:.1f} MB y el máximo permitido es 10 MB."
        )

    archivo.seek(0)
    firma = archivo.read(len(FIRMA_PDF))
    archivo.seek(0)
    if firma != FIRMA_PDF:
        raise serializers.ValidationError(
            "El contenido del archivo no corresponde a un PDF válido."
        )

    return archivo