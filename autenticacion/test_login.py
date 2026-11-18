"""
Pruebas del inicio de sesión (HU-03).

Casos de prueba de la guía del Sprint 1:
  - CP-03: login exitoso y persistencia de la sesión con el token.
  - CP-04: bloqueo por credenciales inválidas o por omisión del CAPTCHA.

El CAPTCHA se simula con @patch: así las pruebas no dependen de Google ni
de internet. El servicio real del CAPTCHA ya se probó en test_captcha.py.
"""

from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from usuarios.models import Rol, Usuario

from .captcha import CaptchaNoDisponible

CORREO = "ana@correo.com"
CLAVE = "ClaveSegura123"


# El @patch sobre la clase se aplica a TODAS sus pruebas: en cada una,
# verificar_captcha queda reemplazado por un simulador que responde True,
# y el simulador llega como parámetro (captcha_falso).
@patch("autenticacion.serializers.verificar_captcha", return_value=True)
class LoginTests(APITestCase):
    def setUp(self):
        """Preparación común: un autor registrado y las direcciones de los endpoints."""
        self.usuario = Usuario.objects.create_user(
            CORREO, CLAVE,
            nombres="Ana", apellidos="Pérez",
            afiliacion="Universidad del Valle", pais="Colombia",
        )
        self.usuario.asignar_rol(Rol.Nombre.AUTOR)

        self.url_login = reverse("autenticacion:login")
        self.url_refresh = reverse("autenticacion:refresh")
        self.url_sesion = reverse("autenticacion:sesion")

    def iniciar_sesion(self, correo=CORREO, clave=CLAVE, captcha="token-captcha"):
        """Atajo: envía el formulario de login con los datos indicados."""
        return self.client.post(
            self.url_login,
            {"correo": correo, "clave": clave, "captcha": captcha},
            format="json",
        )

    # ---------------------------------------------------------------- CP-03
    def test_login_exitoso_devuelve_tokens_y_datos_del_usuario(self, captcha_falso):
        # Ejecutar
        respuesta = self.iniciar_sesion()

        # Verificar: 200 con los dos tokens y los datos del usuario, sin la clave.
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertIn("access", respuesta.data)
        self.assertIn("refresh", respuesta.data)
        self.assertEqual(respuesta.data["usuario"]["correo"], CORREO)
        self.assertNotIn("clave", respuesta.data)

        # Verificar: quedó registrada la fecha del último inicio de sesión.
        self.usuario.refresh_from_db()
        self.assertIsNotNone(self.usuario.last_login)

    def test_el_token_permite_consultar_la_sesion(self, captcha_falso):
        # Preparar: iniciar sesión y guardar el token de acceso.
        access = self.iniciar_sesion().data["access"]

        # Ejecutar: consultar la sesión enviando el token en el encabezado.
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        respuesta = self.client.get(self.url_sesion)

        # Verificar: el servidor reconoce al usuario a partir del token.
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["correo"], CORREO)

    def test_sesion_sin_token_devuelve_401(self, captcha_falso):
        respuesta = self.client.get(self.url_sesion)
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_entrega_un_nuevo_token_de_acceso(self, captcha_falso):
        # Preparar
        refresh = self.iniciar_sesion().data["refresh"]

        # Ejecutar: pedir un token de acceso nuevo con el token de renovación.
        respuesta = self.client.post(self.url_refresh, {"refresh": refresh}, format="json")

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertIn("access", respuesta.data)

    # ---------------------------------------------------------------- CP-04
    def test_clave_incorrecta_devuelve_401(self, captcha_falso):
        respuesta = self.iniciar_sesion(clave="ClaveEquivocada1")

        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(str(respuesta.data["detail"]), "Correo o clave incorrectos.")

    def test_correo_inexistente_devuelve_el_mismo_mensaje(self, captcha_falso):
        """Seguridad: no se revela si el correo está registrado."""
        clave_mala = self.iniciar_sesion(clave="ClaveEquivocada1")
        correo_inexistente = self.iniciar_sesion(correo="nadie@correo.com")

        # Verificar: mismo código y mismo mensaje en ambos casos.
        self.assertEqual(correo_inexistente.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(correo_inexistente.data["detail"], clave_mala.data["detail"])

    def test_usuario_desactivado_no_puede_iniciar_sesion(self, captcha_falso):
        # Preparar: desactivar la cuenta (borrado lógico de la HU-12).
        self.usuario.activo = False
        self.usuario.save()

        # Ejecutar: intentar entrar con la clave correcta.
        respuesta = self.iniciar_sesion()

        # Verificar: se niega el acceso aunque la clave sea correcta.
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_de_usuario_desactivado_deja_de_servir(self, captcha_falso):
        # Preparar: el usuario inicia sesión y después lo desactivan.
        access = self.iniciar_sesion().data["access"]
        self.usuario.activo = False
        self.usuario.save()

        # Ejecutar: usar el token que obtuvo antes de ser desactivado.
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        respuesta = self.client.get(self.url_sesion)

        # Verificar: el token deja de funcionar de inmediato, porque Simple JWT
        # consulta is_active (es decir, el campo activo) en cada petición.
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_captcha_invalido_devuelve_400(self, captcha_falso):
        # Preparar: Google rechaza el CAPTCHA.
        captcha_falso.return_value = False

        # Ejecutar
        respuesta = self.iniciar_sesion()

        # Verificar: 400 con el error en el campo captcha.
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("captcha", respuesta.data)

    def test_sin_captcha_devuelve_400_y_no_consulta_a_google(self, captcha_falso):
        # Ejecutar: omitir el CAPTCHA.
        respuesta = self.client.post(
            self.url_login, {"correo": CORREO, "clave": CLAVE}, format="json"
        )

        # Verificar: 400 sin llegar a consultar a Google.
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("captcha", respuesta.data)
        captcha_falso.assert_not_called()

    def test_captcha_no_disponible_devuelve_503(self, captcha_falso):
        # Preparar: simular que Google no responde.
        captcha_falso.side_effect = CaptchaNoDisponible()

        # Ejecutar
        respuesta = self.iniciar_sesion()

        # Verificar: se falla cerrado con 503 y no se entregan tokens.
        self.assertEqual(respuesta.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertNotIn("access", respuesta.data)
        
    # ---------------------------------------------------------------- HU-04
    def test_login_con_multiples_roles_devuelve_arreglo_completo(self, captcha_falso):
        """Verifica que el login incluya todos los roles asignados al usuario."""
        # Preparar: asignar un segundo rol válido del catálogo Rol.Nombre
        segundo_rol = next(r for r in Rol.Nombre.values if r != Rol.Nombre.AUTOR)
        self.usuario.asignar_rol(segundo_rol)

        # Ejecutar
        respuesta = self.iniciar_sesion()

        # Verificar: 200 OK y el arreglo usuario.roles contiene ambos roles
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertIn("roles", respuesta.data["usuario"])
        self.assertCountEqual(
            respuesta.data["usuario"]["roles"],
            [Rol.Nombre.AUTOR, segundo_rol],
        )

    def test_sesion_devuelve_arreglo_dinamico_de_roles(self, captcha_falso):
        """Verifica que /api/auth/sesion/ conserve los roles al recargar sesión."""
        # Preparar: asignar dos roles e iniciar sesión para obtener el token
        segundo_rol = next(r for r in Rol.Nombre.values if r != Rol.Nombre.AUTOR)
        self.usuario.asignar_rol(segundo_rol)
        access = self.iniciar_sesion().data["access"]

        # Ejecutar: consultar el endpoint de sesión con el token Bearer
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        respuesta = self.client.get(self.url_sesion)

        # Verificar: la respuesta entrega ambos roles autorizados
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertCountEqual(
            respuesta.data["roles"],
            [Rol.Nombre.AUTOR, segundo_rol],
        )