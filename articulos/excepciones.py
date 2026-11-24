"""
Errores propios del dominio de artículos.

En DRF, una excepción que hereda de APIException se convierte automáticamente
en una respuesta HTTP con su código de estado y su mensaje: {"detail": "..."}.
"""

from rest_framework import status
from rest_framework.exceptions import APIException


class PostulacionCerrada(APIException):
    """
    No se pueden postular artículos en este momento. Responde 400 (HU-14.2).

    Casos: no hay una edición vigente de la conferencia, o ya pasó su
    límite de postulación (HU-13). La vista indica el mensaje de cada caso.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "La postulación de artículos está cerrada."
    default_code = "postulacion_cerrada"