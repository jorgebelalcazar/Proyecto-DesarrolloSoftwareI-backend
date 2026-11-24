"""
Pruebas del cierre de sesión (HU-05).

Endpoint: POST /api/auth/logout/   con {"refresh": "<token>"}

Cubren:
  - HU-05.1: el token de renovación queda en la lista negra (204).
  - HU-05.QA: después del logout ese token ya no sirve para renovar la
    sesión, así que las rutas protegidas quedan bloqueadas.
  - Errores: sin token (400); token mal formado, vencido, ya cerrado o de
    acceso en lugar de renovación (401).
  - El logout funciona aunque el token de acceso ya haya vencido.
"""

from datetime import timedelta
from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from usuarios.models import Usuario

CORREO = "ana@correo.com"
CLAVE = "ClaveSegura123"
MENSAJE_SESION_NO_VALIDA = "La sesión no es válida, ya venció o ya se cerró."


class LogoutTests(APITestCase):
    def setUp(self):
        """Preparación común: un usuario con una sesión abierta."""
        self.usuario = Usuario.objects.create_user(
            CORREO, CLAVE,
            nombres="Ana", apellidos="Pérez",
            afiliacion="Universidad del Valle", pais="Colombia",
        )
        self.usuario.asignar_rol("AUTOR")

        # Los mismos tokens que entrega el login (HU-03).
        self.refresh = RefreshToken.for_user(self.usuario)

        self.url = reverse("autenticacion:logout")
        self.url_refresh = reverse("autenticacion:refresh")

    def cerrar_sesion(self, refresh):
        """Atajo: envía el token de renovación al logout."""
        return self.client.post(self.url, {"refresh": str(refresh)}, format="json")

    def renovar(self, refresh):
        """Atajo: pide un token de acceso nuevo con el token de renovación."""
        return self.client.post(self.url_refresh, {"refresh": str(refresh)}, format="json")

    def assert_sesion_no_valida(self, respuesta):
        """Verifica el 401 único del logout."""
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(str(respuesta.data["detail"]), MENSAJE_SESION_NO_VALIDA)

    # ------------------------------------------- HU-05.1: logout exitoso
    def test_logout_pone_el_token_en_la_lista_negra(self):
        respuesta = self.cerrar_sesion(self.refresh)

        # Verificar: 204 sin cuerpo.
        self.assertEqual(respuesta.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(respuesta.content)

        # Verificar: el token quedó en la tabla de la lista negra.
        self.assertTrue(
            BlacklistedToken.objects.filter(token__jti=self.refresh["jti"]).exists()
        )

    # --------------------------- HU-05.QA: bloqueo después del logout
    def test_antes_del_logout_el_token_si_renueva_la_sesion(self):
        """Prueba de control: confirma que el 401 de abajo se debe al logout."""
        respuesta = self.renovar(self.refresh)

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertIn("access", respuesta.data)

    def test_despues_del_logout_el_token_ya_no_renueva_la_sesion(self):
        self.cerrar_sesion(self.refresh)

        respuesta = self.renovar(self.refresh)

        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_cierra_solo_la_sesion_de_ese_token(self):
        """Una sesión abierta en otro dispositivo sigue funcionando."""
        otro_dispositivo = RefreshToken.for_user(self.usuario)

        self.cerrar_sesion(self.refresh)

        self.assertEqual(self.renovar(otro_dispositivo).status_code, status.HTTP_200_OK)

    # ------------------------------------------------------------ Errores
    def test_sin_token_devuelve_400(self):
        respuesta = self.client.post(self.url, {}, format="json")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("refresh", respuesta.data)

    def test_cerrar_la_misma_sesion_dos_veces_devuelve_401(self):
        self.cerrar_sesion(self.refresh)

        self.assert_sesion_no_valida(self.cerrar_sesion(self.refresh))

    def test_token_mal_formado_devuelve_401(self):
        self.assert_sesion_no_valida(self.cerrar_sesion("esto-no-es-un-token"))

    def test_token_de_acceso_en_lugar_de_renovacion_devuelve_401(self):
        self.assert_sesion_no_valida(self.cerrar_sesion(self.refresh.access_token))

    def test_token_vencido_devuelve_401(self):
        # Preparar: un token de renovación que venció hace un minuto.
        vencido = RefreshToken.for_user(self.usuario)
        vencido.set_exp(lifetime=-timedelta(minutes=1))

        self.assert_sesion_no_valida(self.cerrar_sesion(vencido))

    # --------------------------------- Token de acceso vencido o inválido
    def test_logout_funciona_aunque_el_token_de_acceso_no_sirva(self):
        """
        La credencial del logout es el token de renovación. Un encabezado
        Authorization vencido o falso no debe impedir cerrar la sesión.
        """
        self.client.credentials(HTTP_AUTHORIZATION="Bearer token-de-acceso-vencido")

        respuesta = self.cerrar_sesion(self.refresh)

        self.assertEqual(respuesta.status_code, status.HTTP_204_NO_CONTENT)


@patch("autenticacion.serializers.verificar_captcha", return_value=True)
class FlujoSesionTests(APITestCase):
    """La sesión completa, de punta a punta: login, uso, logout y bloqueo."""

    def test_login_logout_y_la_sesion_queda_cerrada(self, captcha_falso):
        Usuario.objects.create_user(
            CORREO, CLAVE,
            nombres="Ana", apellidos="Pérez",
            afiliacion="Universidad del Valle", pais="Colombia",
        )

        # Paso 1 (HU-03): iniciar sesión.
        login = self.client.post(
            reverse("autenticacion:login"),
            {"correo": CORREO, "clave": CLAVE, "captcha": "token-captcha"},
            format="json",
        )
        refresh = login.data["refresh"]

        # Paso 2 (HU-05): cerrar sesión.
        logout = self.client.post(
            reverse("autenticacion:logout"), {"refresh": refresh}, format="json"
        )
        self.assertEqual(logout.status_code, status.HTTP_204_NO_CONTENT)

        # Paso 3 (HU-05.QA): el token ya no da acceso nuevo.
        renovacion = self.client.post(
            reverse("autenticacion:refresh"), {"refresh": refresh}, format="json"
        )
        self.assertEqual(renovacion.status_code, status.HTTP_401_UNAUTHORIZED)