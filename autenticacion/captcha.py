"""
Servicio de verificación de Google reCAPTCHA v2 (HU-03.2).

Flujo completo del CAPTCHA:
  1. En React, el usuario marca "No soy un robot" y Google le entrega
     un token de CAPTCHA.
  2. React envía ese token a nuestra API junto con el correo y la clave.
  3. Este servicio le pregunta a Google, de servidor a servidor, si el token
     es válido. Solo el back-end conoce la clave secreta.

Se usa la librería estándar de Python (urllib), sin dependencias adicionales.
"""

import json
import logging
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

# Registro de eventos: deja constancia en la consola del servidor cuando
# Google no responde, para poder diagnosticar el problema.
logger = logging.getLogger(__name__)


class CaptchaNoDisponible(Exception):
    """
    Google no respondió a tiempo o respondió algo que no se pudo leer.

    Es distinto de un CAPTCHA inválido: aquí el problema es la conexión,
    no el usuario. La vista lo convierte en una respuesta 503.
    """


def verificar_captcha(token, ip=None):
    """
    Pregunta a Google si un token de reCAPTCHA es válido.

    Parámetros:
      - token: el token que entregó el widget de Google en el navegador.
      - ip: dirección IP del usuario (opcional; Google la usa como dato extra).

    Posibles resultados:
      - True:  Google confirma que el token es válido.
      - False: el token está vacío, es falso, ya se usó o venció.
      - Lanza CaptchaNoDisponible: Google no respondió (problema de red).
    """
    # Paso 1: sin token no hay nada que verificar.
    # Respondemos False sin consultar a Google, para no gastar una petición.
    if not token:
        return False

    # Paso 2: preparar los datos que pide Google.
    #   - secret:   nuestra clave secreta (demuestra que la petición es nuestra).
    #   - response: el token que entregó el widget.
    #   - remoteip: la IP del usuario (opcional).
    datos = {"secret": settings.RECAPTCHA_SECRET_KEY, "response": token}
    if ip:
        datos["remoteip"] = ip

    # Google espera un formulario codificado (secret=...&response=...),
    # convertido a bytes para enviarlo en el cuerpo de la petición POST.
    peticion = Request(
        settings.RECAPTCHA_URL_VERIFICACION,
        data=urlencode(datos).encode(),
        method="POST",
    )

    # Paso 3: enviar la petición con un tiempo límite.
    # Sin tiempo límite, si Google tardara, el login quedaría esperando
    # indefinidamente.
    try:
        with urlopen(peticion, timeout=settings.RECAPTCHA_TIEMPO_LIMITE) as respuesta:
            resultado = json.load(respuesta)
    except (OSError, ValueError) as error:
        # OSError cubre los problemas de red: sin conexión, tiempo agotado,
        # servidor caído. ValueError cubre una respuesta que no es JSON válido.
        # Fallamos cerrado: si no podemos verificar, NO dejamos pasar.
        logger.warning("No fue posible verificar el reCAPTCHA: %s", error)
        raise CaptchaNoDisponible() from error

    # Paso 4: Google responde un JSON como {"success": true, ...}.
    # Comparamos con "is True" para aceptar solo un verdadero real,
    # y no cualquier valor que se parezca a verdadero.
    return resultado.get("success") is True