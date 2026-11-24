"""
Errores propios del dominio de la conferencia.

En DRF, una excepción que hereda de APIException se convierte automáticamente
en una respuesta HTTP con su código de estado y su mensaje: {"detail": "..."}.
"""

from rest_framework import status
from rest_framework.exceptions import APIException


class RubricaNoEditable(APIException):
    """
    La rúbrica de la edición ya no se puede cambiar. Responde 400 (HU-22.2).

    Cuando cierra la postulación empieza la revisión: desde ese momento todos
    los artículos deben evaluarse con los mismos criterios.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "La rúbrica de esta edición ya no se puede modificar."
    default_code = "rubrica_no_editable"