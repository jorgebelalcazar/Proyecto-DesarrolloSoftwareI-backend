"""
Pruebas de la confirmación del PIN y el cambio de clave (HU-07).

Cubren el caso de prueba CP-06 de la subtarea de QA HU-07.5:
  - PIN válido: cambia la clave y el PIN queda usado;
  - PIN erróneo: no cambia la clave y suma un intento;
  - PIN expirado: no cambia la clave.
Y además: PIN reutilizado, intentos agotados, correo inexistente,
cuenta desactivada, validaciones de formato y el flujo completo de la
recuperación (HU-06 + HU-07 + login).

Los códigos se crean directamente con el modelo y un PIN conocido, para
probar este paso sin depender del correo del paso 1.
"""

import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import authenticate
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from usuarios.models import CodigoRecuperacion, Usuario

CORREO = "ana@correo.com"
CLAVE_ACTUAL = "ClaveSegura123"
CLAVE_NUEVA = "NuevaClave456"
PIN = "123456"
MENSAJE_PIN_INVALIDO = "El código no es válido o ya venció. Verifíquelo o solicite uno nuevo."


class ConfirmarPinTests(APITestCase):
    def setUp(self):
        """Preparación común: un usuario activo con un PIN vigente."""
        self.usuario = Usuario.objects.create_user(
            CORREO, CLAVE_ACTUAL,
            nombres="Ana", apellidos="Pérez",
            afiliacion="Universidad del Valle", pais="Colombia",
        )
        self.codigo = self.crear_codigo(PIN)
        self.url = reverse("autenticacion:confirmar-pin")

    def crear_codigo(self, pin):
        """Crea un código de recuperación con el PIN indicado, como lo haría la HU-06."""
        codigo = CodigoRecuperacion(usuario=self.usuario)
        codigo.asignar_pin(pin)
        codigo.save()
        return codigo

    def confirmar(self, pin=PIN, correo=CORREO, clave=CLAVE_NUEVA, confirmacion=None):
        """Atajo: envía el formulario del paso 2."""
        return self.client.post(
            self.url,
            {
                "correo": correo,
                "pin": pin,
                "clave": clave,
                "confirmacion_clave": confirmacion or clave,
            },
            format="json",
        )

    def assert_clave_sin_cambios(self):
        """Verifica que la clave del usuario siga siendo la original."""
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(CLAVE_ACTUAL))

    def assert_pin_rechazado(self, respuesta):
        """Verifica la respuesta única para cualquier PIN que no sirve."""
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(str(respuesta.data["detail"]), MENSAJE_PIN_INVALIDO)

    # ------------------------------------------------- CP-06: PIN válido
    def test_pin_valido_cambia_la_clave_y_marca_el_pin_como_usado(self):
        # Ejecutar: confirmar con el correo en mayúsculas.
        respuesta = self.confirmar(correo="ANA@Correo.com")

        # Verificar: 200 y la clave nueva funciona para iniciar sesión.
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(authenticate(correo=CORREO, password=CLAVE_NUEVA))
        self.assertIsNone(authenticate(correo=CORREO, password=CLAVE_ACTUAL))

        # Verificar: el PIN quedó usado (HU-07.2).
        self.codigo.refresh_from_db()
        self.assertTrue(self.codigo.usado)

    # ------------------------------------------------ CP-06: PIN erróneo
    def test_pin_erroneo_no_cambia_la_clave_y_suma_un_intento(self):
        respuesta = self.confirmar(pin="654321")

        self.assert_pin_rechazado(respuesta)
        self.assert_clave_sin_cambios()
        self.codigo.refresh_from_db()
        self.assertEqual(self.codigo.intentos, 1)

    def test_tras_tres_errores_ni_el_pin_correcto_sirve(self):
        # Preparar: agotar los 3 intentos.
        for _ in range(CodigoRecuperacion.MAX_INTENTOS):
            self.confirmar(pin="000000")

        # Ejecutar: ahora sí con el PIN correcto.
        respuesta = self.confirmar(pin=PIN)

        # Verificar: el código quedó inutilizable.
        self.assert_pin_rechazado(respuesta)
        self.assert_clave_sin_cambios()

    # ----------------------------------------------- CP-06: PIN expirado
    def test_pin_expirado_no_cambia_la_clave(self):
        # Preparar: el código venció hace un minuto.
        self.codigo.expira_en = timezone.now() - timedelta(minutes=1)
        self.codigo.save()

        respuesta = self.confirmar()

        self.assert_pin_rechazado(respuesta)
        self.assert_clave_sin_cambios()

    # ------------------------------------------------- Otros casos de seguridad
    def test_pin_reutilizado_es_rechazado(self):
        # Preparar: usar el PIN una vez.
        self.confirmar()

        # Ejecutar: intentar usarlo otra vez con otra clave.
        respuesta = self.confirmar(clave="OtraClave789")

        # Verificar: rechazado; sigue valiendo la clave del primer cambio.
        self.assert_pin_rechazado(respuesta)
        self.assertIsNotNone(authenticate(correo=CORREO, password=CLAVE_NUEVA))

    def test_solo_sirve_el_pin_mas_reciente(self):
        # Preparar: un PIN nuevo invalida el anterior, como lo hace la HU-06.
        self.codigo.usado = True
        self.codigo.save()
        self.crear_codigo("777777")

        # Verificar: el PIN anterior ya no sirve, el nuevo sí.
        self.assert_pin_rechazado(self.confirmar(pin=PIN))
        self.assertEqual(self.confirmar(pin="777777").status_code, status.HTTP_200_OK)

    def test_correo_inexistente_recibe_el_mismo_mensaje(self):
        """No se revela si el correo está registrado."""
        respuesta = self.confirmar(correo="nadie@correo.com")
        self.assert_pin_rechazado(respuesta)

    def test_cuenta_desactivada_no_puede_cambiar_la_clave(self):
        # Preparar: la cuenta se desactivó después de pedir el PIN (HU-12).
        self.usuario.activo = False
        self.usuario.save()

        respuesta = self.confirmar()

        self.assert_pin_rechazado(respuesta)
        self.assert_clave_sin_cambios()

    # --------------------------------------- Formato: no gasta intentos
    def test_clave_debil_devuelve_400_sin_gastar_intentos(self):
        respuesta = self.confirmar(clave="clavedebil")

        # Verificar: error en el campo clave, y el código intacto.
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("clave", respuesta.data)
        self.codigo.refresh_from_db()
        self.assertEqual(self.codigo.intentos, 0)
        self.assertFalse(self.codigo.usado)

    def test_claves_distintas_devuelve_400(self):
        respuesta = self.confirmar(confirmacion="OtraClave789")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("confirmacion_clave", respuesta.data)
        self.assert_clave_sin_cambios()

    def test_pin_con_formato_invalido_devuelve_400(self):
        for pin in ("12345", "1234567", "12a456", ""):
            with self.subTest(pin=pin):
                respuesta = self.confirmar(pin=pin)
                self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("pin", respuesta.data)

        # Verificar: ninguno de estos envíos gastó intentos.
        self.codigo.refresh_from_db()
        self.assertEqual(self.codigo.intentos, 0)


@patch("autenticacion.serializers.verificar_captcha", return_value=True)
class FlujoRecuperacionTests(APITestCase):
    """La recuperación completa, de punta a punta, como la hace el usuario."""

    def test_solicitar_pin_confirmar_e_iniciar_sesion(self, captcha_falso):
        # Preparar: un usuario que olvidó su clave.
        Usuario.objects.create_user(
            CORREO, CLAVE_ACTUAL,
            nombres="Ana", apellidos="Pérez",
            afiliacion="Universidad del Valle", pais="Colombia",
        )

        # Paso 1 (HU-06): solicitar el PIN y leerlo del correo recibido.
        self.client.post(
            reverse("autenticacion:solicitar-pin"),
            {"correo": CORREO, "captcha": "token-captcha"},
            format="json",
        )
        pin = re.search(r"\b(\d{6})\b", mail.outbox[0].body).group(1)

        # Paso 2 (HU-07): confirmar el PIN con la nueva clave.
        confirmacion = self.client.post(
            reverse("autenticacion:confirmar-pin"),
            {"correo": CORREO, "pin": pin, "clave": CLAVE_NUEVA, "confirmacion_clave": CLAVE_NUEVA},
            format="json",
        )
        self.assertEqual(confirmacion.status_code, status.HTTP_200_OK)

        # Paso 3 (HU-03): iniciar sesión con la nueva clave.
        login = self.client.post(
            reverse("autenticacion:login"),
            {"correo": CORREO, "clave": CLAVE_NUEVA, "captcha": "token-captcha"},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        self.assertIn("access", login.data)