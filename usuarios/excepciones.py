"""
Errores propios del dominio de usuarios.

En DRF, una excepción que hereda de APIException se convierte automáticamente
en una respuesta HTTP con su código de estado y su mensaje. Así, las vistas
solo lanzan el error y DRF arma la respuesta: {"detail": "mensaje"}.
"""

from rest_framework import status
from rest_framework.exceptions import APIException


class BajaNoPermitida(APIException):
    """
    La cuenta no se puede desactivar. Responde 400 (HU-12).

    Casos: desactivar la propia cuenta, una cuenta ya desactivada o el
    último Administrador activo. La vista indica el mensaje de cada caso.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "No es posible desactivar esta cuenta."
    default_code = "baja_no_permitida"