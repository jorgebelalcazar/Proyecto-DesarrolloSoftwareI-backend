"""
Errores propios de la autenticación.

En DRF, una excepción que hereda de APIException se convierte automáticamente
en una respuesta HTTP con su código de estado y su mensaje. Así, las vistas
solo lanzan el error y DRF arma la respuesta.
"""

from rest_framework import status
from rest_framework.exceptions import APIException


class CredencialesInvalidas(APIException):
    """
    Correo o clave incorrectos, o cuenta desactivada. Responde 401.

    El mensaje es el MISMO en todos los casos, a propósito: si dijera
    "ese correo no existe", un atacante podría averiguar qué correos
    están registrados (enumeración de usuarios).
    """

    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Correo o clave incorrectos."
    default_code = "credenciales_invalidas"


class ServicioCaptchaNoDisponible(APIException):
    """
    Google no respondió al verificar el CAPTCHA. Responde 503.

    El error no es culpa del usuario, por eso no es un 400: el código 503
    significa "servicio no disponible temporalmente".
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = (
        "No fue posible verificar el CAPTCHA en este momento. "
        "Intente de nuevo en unos minutos."
    )
    default_code = "captcha_no_disponible"