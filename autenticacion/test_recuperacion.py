"""
Pruebas de la solicitud del PIN de recuperación (HU-06).

Cubren lo que pide la subtarea de QA HU-06.5:
  - el envío del correo con el PIN;
  - la vigencia de 15 minutos;
  - los correos inexistentes (misma respuesta, sin envío).

Los correos no salen a internet: durante las pruebas Django los guarda en
la lista "mail.outbox", donde se puede revisar su destinatario y contenido.
El CAPTCHA se simula con @patch, igual que en las pruebas del login.
"""

import re
from datetime import timedelta
from smtplib import SMTPException
from unittest.mock import patch

from django.core import mail
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from usuarios.models import CodigoRecuperacion, Rol, Usuario

from .recuperacion import ESPERA_ENTRE_SOLICITUDES_SEGUNDOS, generar_pin

CORREO = "ana@correo.com"


def pin_del_correo(mensaje):
    """Extrae el PIN de 6 dígitos del cuerpo de un correo."""
    return re.search(r"\b(\d{6})\b", mensaje.body).group(1)


@patch("autenticacion.serializers.verificar_captcha", return_value=True)
class SolicitarPinTests(APITestCase):
    def setUp(self):
        """Preparación común: un autor activo y la dirección del endpoint."""
        self.usuario = Usuario.objects.create_user(
            CORREO, "ClaveSegura123",
            nombres="Ana", apellidos="Pérez",
            afiliacion="Universidad del Valle", pais="Colombia",
        )
        self.usuario.asignar_rol(Rol.Nombre.AUTOR)
        self.url = reverse("autenticacion:solicitar-pin")

    def solicitar(self, correo=CORREO, captcha="token-captcha"):
        """Atajo: envía el formulario "Olvidé mi clave"."""
        return self.client.post(
            self.url, {"correo": correo, "captcha": captcha}, format="json"
        )

    def envejecer_codigos(self):
        """Simula que ya pasó el tiempo de espera desde la última solicitud."""
        hace_rato = timezone.now() - timedelta(seconds=ESPERA_ENTRE_SOLICITUDES_SEGUNDOS + 1)
        CodigoRecuperacion.objects.update(creado_en=hace_rato)

    # -------------------------------------------------- Envío del PIN
    def test_correo_registrado_recibe_un_pin_de_6_digitos(self, captcha_falso):
        # Ejecutar: solicitar el PIN escribiendo el correo con mayúsculas.
        respuesta = self.solicitar(correo="ANA@Correo.com")

        # Verificar: 200 y un correo enviado a la cuenta.
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [CORREO])

        # Verificar: el correo trae un PIN de 6 dígitos que corresponde al guardado.
        pin = pin_del_correo(mail.outbox[0])
        codigo = CodigoRecuperacion.objects.get(usuario=self.usuario)
        self.assertTrue(codigo.verificar_pin(pin))

    def test_el_pin_se_guarda_como_hash(self, captcha_falso):
        self.solicitar()
        pin = pin_del_correo(mail.outbox[0])
        codigo = CodigoRecuperacion.objects.get(usuario=self.usuario)

        # Verificar: en la base de datos no aparece el PIN en texto plano.
        self.assertNotIn(pin, codigo.pin_hash)

    def test_el_pin_vence_en_15_minutos(self, captcha_falso):
        self.solicitar()
        codigo = CodigoRecuperacion.objects.get(usuario=self.usuario)

        minutos = (codigo.expira_en - codigo.creado_en).total_seconds() / 60
        self.assertAlmostEqual(minutos, 15, delta=0.1)
        self.assertTrue(codigo.esta_disponible())

    def test_el_correo_incluye_version_html(self, captcha_falso):
        self.solicitar()

        # alternatives guarda las versiones adicionales del correo, como la HTML.
        html, tipo = mail.outbox[0].alternatives[0]
        self.assertEqual(tipo, "text/html")
        self.assertIn(pin_del_correo(mail.outbox[0]), html)

    # ------------------------------------- Sin revelar qué correos existen
    def test_correo_inexistente_recibe_la_misma_respuesta_sin_envio(self, captcha_falso):
        registrado = self.solicitar()
        inexistente = self.solicitar(correo="nadie@correo.com")

        # Verificar: mismo código y mismo cuerpo de respuesta.
        self.assertEqual(inexistente.status_code, status.HTTP_200_OK)
        self.assertEqual(inexistente.data, registrado.data)

        # Verificar: solo se envió el correo de la cuenta registrada.
        self.assertEqual(len(mail.outbox), 1)

    def test_cuenta_desactivada_no_recibe_pin(self, captcha_falso):
        # Preparar: cuenta dada de baja (HU-12).
        self.usuario.activo = False
        self.usuario.save()

        # Ejecutar
        respuesta = self.solicitar()

        # Verificar: misma respuesta, pero sin correo ni código.
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(CodigoRecuperacion.objects.exists())

    # ------------------------------------------- Solicitudes repetidas
    def test_solicitudes_seguidas_no_envian_otro_correo(self, captcha_falso):
        """Protección contra el llenado de bandejas: una solicitud por minuto."""
        self.solicitar()
        respuesta = self.solicitar()

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(CodigoRecuperacion.objects.count(), 1)

    def test_un_pin_nuevo_invalida_el_anterior(self, captcha_falso):
        # Preparar: un primer PIN, y dejar pasar el tiempo de espera.
        self.solicitar()
        self.envejecer_codigos()

        # Ejecutar: pedir un segundo PIN.
        self.solicitar()

        # Verificar: dos correos, pero solo el último código está disponible.
        self.assertEqual(len(mail.outbox), 2)
        anterior, nuevo = CodigoRecuperacion.objects.order_by("id")
        self.assertTrue(anterior.usado)
        self.assertTrue(nuevo.esta_disponible())

    # ------------------------------------------------ Validaciones y fallos
    def test_sin_captcha_o_correo_invalido_devuelve_400(self, captcha_falso):
        casos = {
            "captcha": {"correo": CORREO},
            "correo": {"correo": "no-es-un-correo", "captcha": "token-captcha"},
        }
        for campo, datos in casos.items():
            with self.subTest(campo=campo):
                respuesta = self.client.post(self.url, datos, format="json")
                self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(campo, respuesta.data)
        self.assertEqual(len(mail.outbox), 0)

    def test_captcha_invalido_devuelve_400(self, captcha_falso):
        captcha_falso.return_value = False

        respuesta = self.solicitar()

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("captcha", respuesta.data)
        self.assertEqual(len(mail.outbox), 0)

    @patch("autenticacion.recuperacion.send_mail", side_effect=SMTPException("servidor caído"))
    def test_si_el_correo_falla_responde_503_y_no_guarda_el_pin(self, correo_falso, captcha_falso):
        # Ejecutar: el servidor de correo rechaza el envío.
        respuesta = self.solicitar()

        # Verificar: 503 y ningún código guardado (la transacción se deshizo).
        self.assertEqual(respuesta.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(CodigoRecuperacion.objects.exists())


class GenerarPinTests(APITestCase):
    def test_el_pin_tiene_siempre_6_digitos(self):
        # Se generan muchos PIN para cubrir los que empiezan por cero.
        for _ in range(200):
            pin = generar_pin()
            self.assertRegex(pin, r"^\d{6}$")