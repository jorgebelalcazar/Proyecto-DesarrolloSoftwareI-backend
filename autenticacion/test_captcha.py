"""
Pruebas del servicio de verificación de reCAPTCHA (HU-03.2).

Las pruebas NO se conectan a Google: reemplazan la función urlopen por un
"simulador" (mock) que devuelve la respuesta que necesitamos. Así:
  - no dependen de internet;
  - son rápidas;
  - pueden simular casos difíciles de provocar, como que Google no responda.
"""

import io
import json
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from django.test import SimpleTestCase, override_settings

from .captcha import CaptchaNoDisponible, verificar_captcha


def respuesta_google(datos):
    """
    Construye una respuesta HTTP falsa de Google con el JSON indicado.

    urlopen se usa con "with", así que el simulador debe funcionar como
    administrador de contexto: __enter__ devuelve el cuerpo de la respuesta.
    """
    respuesta = MagicMock()
    respuesta.__enter__.return_value = io.BytesIO(json.dumps(datos).encode())
    return respuesta


# override_settings cambia la configuración solo durante estas pruebas.
@override_settings(RECAPTCHA_SECRET_KEY="secreto-de-prueba", RECAPTCHA_TIEMPO_LIMITE=3)
class VerificarCaptchaTests(SimpleTestCase):
    """SimpleTestCase: pruebas que no necesitan base de datos."""

    # @patch reemplaza urlopen DENTRO del módulo captcha mientras dura la prueba,
    # y entrega el simulador como parámetro (urlopen_falso).
    @patch("autenticacion.captcha.urlopen")
    def test_token_valido_devuelve_true(self, urlopen_falso):
        # Preparar: Google responde que el token es válido.
        urlopen_falso.return_value = respuesta_google({"success": True})

        # Ejecutar y verificar
        self.assertTrue(verificar_captcha("token-valido", "127.0.0.1"))

    @patch("autenticacion.captcha.urlopen")
    def test_token_invalido_devuelve_false(self, urlopen_falso):
        # Preparar: Google rechaza el token.
        urlopen_falso.return_value = respuesta_google(
            {"success": False, "error-codes": ["invalid-input-response"]}
        )

        # Ejecutar y verificar
        self.assertFalse(verificar_captcha("token-falso"))

    @patch("autenticacion.captcha.urlopen")
    def test_token_vacio_devuelve_false_sin_consultar_a_google(self, urlopen_falso):
        # Ejecutar y verificar: un token vacío se rechaza de inmediato.
        self.assertFalse(verificar_captcha(""))

        # Verificar: no se hizo ninguna petición a Google.
        urlopen_falso.assert_not_called()

    @patch("autenticacion.captcha.urlopen")
    def test_sin_conexion_con_google_lanza_captcha_no_disponible(self, urlopen_falso):
        # Preparar: simular que no hay red.
        urlopen_falso.side_effect = URLError("sin conexión")

        # Ejecutar y verificar: el servicio falla cerrado con su propio error.
        with self.assertRaises(CaptchaNoDisponible):
            verificar_captcha("token-valido")

    @patch("autenticacion.captcha.urlopen")
    def test_envia_secreto_token_y_tiempo_limite(self, urlopen_falso):
        # Preparar
        urlopen_falso.return_value = respuesta_google({"success": True})

        # Ejecutar
        verificar_captcha("token-de-prueba")

        # Verificar: la petición enviada a Google lleva el secreto y el token...
        peticion = urlopen_falso.call_args.args[0]
        self.assertIn(b"secret=secreto-de-prueba", peticion.data)
        self.assertIn(b"response=token-de-prueba", peticion.data)

        # ...y se hizo con el tiempo límite configurado.
        self.assertEqual(urlopen_falso.call_args.kwargs["timeout"], 3)