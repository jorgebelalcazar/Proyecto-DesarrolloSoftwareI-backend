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

    
class ServicioCorreoNoDisponible(APIException):
    """
    El servidor de correo no aceptó el mensaje con el PIN. Responde 503 (HU-06).

    Como el correo no salió, tampoco se guarda el PIN: el usuario puede
    solicitarlo de nuevo cuando el servicio se recupere.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = (
        "No fue posible enviar el correo en este momento. "
        "Intente de nuevo en unos minutos."
    )
    default_code = "correo_no_disponible"


class PinInvalido(APIException):
    """
    El PIN no sirve para cambiar la clave. Responde 400 (HU-07).

    El mensaje es el mismo para todos los casos (PIN incorrecto, vencido,
    usado, sin intentos o correo inexistente), a propósito: así no se
    revela si el correo existe ni cuántos intentos quedan.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = (
        "El código no es válido o ya venció. "
        "Verifíquelo o solicite uno nuevo."
    )
    default_code = "pin_invalido"