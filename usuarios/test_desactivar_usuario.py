"""
Pruebas de la desactivación de cuentas (HU-12).

Endpoint: DELETE /api/usuarios/{id}/   (baja lógica)

Cubren:
  - HU-12.1: la cuenta queda activo=False con su fecha de desactivación, y
    la fila NO se borra.
  - Acceso: 401 sin token, 403 para el Autor, 404 si no existe.
  - Reglas: el Comité no desactiva Administradores (403); nadie se desactiva
    a sí mismo, ni desactiva una cuenta ya desactivada (400); siempre queda
    un Administrador activo.
  - HU-12.QA: después de la baja la cuenta no puede iniciar sesión, y sus
    tokens anteriores dejan de servir.
"""

from datetime import timedelta
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import MENSAJE_ULTIMO_ADMIN_BAJA, Rol, SinAdministradorActivo, Usuario

CLAVE = "ClaveSegura123"


def crear_usuario(correo, nombres, *roles):
    """Crea un usuario de prueba con los roles indicados."""
    usuario = Usuario.objects.create_user(
        correo, CLAVE,
        nombres=nombres, apellidos="Prueba",
        afiliacion="Universidad del Valle", pais="Colombia",
    )
    for rol in roles:
        usuario.asignar_rol(rol)
    return usuario


class DesactivarUsuarioTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        """Datos comunes, creados UNA vez para todas las pruebas de la clase."""
        cls.admin = crear_usuario("admin@ejemplo.com", "Ana", Rol.Nombre.ADMIN)
        cls.comite = crear_usuario("comite@ejemplo.com", "Carolina", Rol.Nombre.COMITE)
        cls.autor = crear_usuario("autor@ejemplo.com", "Andrés", Rol.Nombre.AUTOR)

    def url(self, usuario):
        """Dirección de la cuenta: /api/usuarios/{id}/."""
        return reverse("usuarios:gestion", args=[usuario.pk])

    def desactivar_como(self, quien, usuario):
        """Atajo: DELETE a la cuenta de "usuario", autenticado como "quien"."""
        self.client.force_authenticate(user=quien)
        return self.client.delete(self.url(usuario))

    def assert_rechazada(self, respuesta, mensaje):
        """Verifica un 400 con el mensaje indicado en "detail"."""
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(str(respuesta.data["detail"]), mensaje)

    # ------------------------------------------------- HU-12.1: baja lógica
    def test_admin_desactiva_una_cuenta_sin_borrarla(self):
        antes = timezone.now()

        respuesta = self.desactivar_como(self.admin, self.autor)

        # Verificar: 204 sin cuerpo.
        self.assertEqual(respuesta.status_code, status.HTTP_204_NO_CONTENT)

        # Verificar: la fila sigue existiendo, desactivada y con su fecha.
        self.autor.refresh_from_db()
        self.assertFalse(self.autor.activo)
        self.assertIsNotNone(self.autor.fecha_desactivacion)
        self.assertGreaterEqual(self.autor.fecha_desactivacion, antes)

        # Verificar: conserva sus roles (es una baja, no un borrado).
        self.assertTrue(self.autor.tiene_rol(Rol.Nombre.AUTOR))

    def test_comite_desactiva_a_un_autor(self):
        respuesta = self.desactivar_como(self.comite, self.autor)

        self.assertEqual(respuesta.status_code, status.HTTP_204_NO_CONTENT)
        self.autor.refresh_from_db()
        self.assertFalse(self.autor.activo)

    def test_gestor_sigue_viendo_la_cuenta_desactivada(self):
        """El GET de la HU-11 muestra el estado y la fecha de la baja."""
        self.desactivar_como(self.admin, self.autor)

        respuesta = self.client.get(self.url(self.autor))

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertFalse(respuesta.data["activo"])
        self.assertIsNotNone(respuesta.data["fecha_desactivacion"])

    # ------------------------------------------------------------- Acceso
    def test_sin_token_devuelve_401(self):
        respuesta = self.client.delete(self.url(self.autor))
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_autor_no_puede_desactivar_cuentas(self):
        respuesta = self.desactivar_como(self.autor, self.comite)

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)
        self.comite.refresh_from_db()
        self.assertTrue(self.comite.activo)

    def test_usuario_inexistente_devuelve_404(self):
        self.client.force_authenticate(user=self.admin)
        respuesta = self.client.delete(reverse("usuarios:gestion", args=[99999]))
        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)

    # ------------------------------------------------------------- Reglas
    def test_comite_no_puede_desactivar_a_un_admin(self):
        respuesta = self.desactivar_como(self.comite, self.admin)

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.activo)

    def test_nadie_puede_desactivar_su_propia_cuenta(self):
        for usuario in (self.admin, self.comite):
            with self.subTest(usuario=usuario.correo):
                respuesta = self.desactivar_como(usuario, usuario)

                self.assert_rechazada(respuesta, "No puede desactivar su propia cuenta.")
                usuario.refresh_from_db()
                self.assertTrue(usuario.activo)

    def test_cuenta_ya_desactivada_conserva_su_fecha_original(self):
        # Preparar: una cuenta desactivada hace un día.
        hace_un_dia = timezone.now() - timedelta(days=1)
        Usuario.objects.filter(pk=self.autor.pk).update(
            activo=False, fecha_desactivacion=hace_un_dia
        )

        respuesta = self.desactivar_como(self.admin, self.autor)

        self.assert_rechazada(respuesta, "La cuenta ya está desactivada.")
        self.autor.refresh_from_db()
        self.assertEqual(self.autor.fecha_desactivacion, hace_un_dia)

    def test_admin_puede_desactivar_a_otro_admin(self):
        otro_admin = crear_usuario("admin2@ejemplo.com", "Beatriz", Rol.Nombre.ADMIN)

        respuesta = self.desactivar_como(self.admin, otro_admin)

        self.assertEqual(respuesta.status_code, status.HTTP_204_NO_CONTENT)

    def test_regla_del_ultimo_admin_responde_400(self):
        """
        Por la API este caso solo ocurre si dos administradores se desactivan
        entre sí al mismo tiempo. Se simula el error del modelo con un mock.
        """
        error = SinAdministradorActivo(MENSAJE_ULTIMO_ADMIN_BAJA)
        with patch.object(Usuario, "desactivar", side_effect=error):
            respuesta = self.desactivar_como(self.admin, self.comite)

        self.assert_rechazada(respuesta, MENSAJE_ULTIMO_ADMIN_BAJA)

    def test_put_sigue_sin_estar_permitido(self):
        self.client.force_authenticate(user=self.admin)
        respuesta = self.client.put(self.url(self.autor), {}, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class ReglaUltimoAdminBajaTests(APITestCase):
    """HU-12 en el modelo: el método desactivar() aplica la regla del último Administrador."""

    def test_el_unico_admin_no_se_puede_desactivar(self):
        admin = crear_usuario("admin@ejemplo.com", "Ana", Rol.Nombre.ADMIN)

        with self.assertRaises(SinAdministradorActivo):
            admin.desactivar()

        admin.refresh_from_db()
        self.assertTrue(admin.activo)
        self.assertIsNone(admin.fecha_desactivacion)

    def test_con_otro_admin_activo_si_se_puede_desactivar(self):
        admin = crear_usuario("admin@ejemplo.com", "Ana", Rol.Nombre.ADMIN)
        crear_usuario("admin2@ejemplo.com", "Beatriz", Rol.Nombre.ADMIN)

        admin.desactivar()

        admin.refresh_from_db()
        self.assertFalse(admin.activo)


@patch("autenticacion.serializers.verificar_captcha", return_value=True)
class AccesoDespuesDeLaBajaTests(APITestCase):
    """
    HU-12.QA: la cuenta desactivada pierde el acceso de inmediato.

    Usa tokens JWT reales (no force_authenticate), porque se prueba
    justamente que los tokens emitidos ANTES de la baja dejen de servir.
    """

    def setUp(self):
        self.admin = crear_usuario("admin@ejemplo.com", "Ana", Rol.Nombre.ADMIN)
        self.autor = crear_usuario("autor@ejemplo.com", "Andrés", Rol.Nombre.AUTOR)

        # Tokens que el autor obtuvo al iniciar sesión, antes de la baja.
        self.refresh = RefreshToken.for_user(self.autor)

    def dar_de_baja_al_autor(self):
        """El Administrador desactiva al autor por la API."""
        self.client.force_authenticate(user=self.admin)
        respuesta = self.client.delete(reverse("usuarios:gestion", args=[self.autor.pk]))
        self.assertEqual(respuesta.status_code, status.HTTP_204_NO_CONTENT)

        # A partir de aquí, las peticiones son del autor, con sus propios tokens.
        self.client.force_authenticate(user=None)

    def iniciar_sesion_autor(self):
        return self.client.post(
            reverse("autenticacion:login"),
            {"correo": "autor@ejemplo.com", "clave": CLAVE, "captcha": "token-captcha"},
            format="json",
        )

    def test_antes_de_la_baja_el_autor_si_inicia_sesion(self, captcha_falso):
        """Prueba de control: confirma que el 401 de abajo se debe a la baja."""
        self.assertEqual(self.iniciar_sesion_autor().status_code, status.HTTP_200_OK)

    def test_despues_de_la_baja_no_puede_iniciar_sesion(self, captcha_falso):
        self.dar_de_baja_al_autor()

        respuesta = self.iniciar_sesion_autor()

        # Verificar: el mismo 401 genérico del login (HU-03); no revela la baja.
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(str(respuesta.data["detail"]), "Correo o clave incorrectos.")

    def test_su_token_de_acceso_anterior_deja_de_servir(self, captcha_falso):
        self.dar_de_baja_al_autor()

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.refresh.access_token}")
        respuesta = self.client.get(reverse("autenticacion:sesion"))

        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_su_token_de_renovacion_anterior_deja_de_servir(self, captcha_falso):
        self.dar_de_baja_al_autor()

        respuesta = self.client.post(
            reverse("autenticacion:refresh"), {"refresh": str(self.refresh)}, format="json"
        )

        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)